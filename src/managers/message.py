"""Messages dispatchers and senders

Working:

* MsgDispatcher
    - CMD_TEXT : MessageHandler

* ConnectionsDispatcher
    - CMD_MSG_CONN: MessageConnHandler
    - PING: PingHandler

* MessageConnHandler
    Reads stream, creates message events, calls message dispatcher to dispatch message events

"""
import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from inspect import isawaitable

from src.avails import BaseDispatcher, InvalidPacket, RemotePeer, Wire, WireData, const, use
from src.avails.connect import MsgConnection, MsgConnectionNoRecv
from src.avails.events import ConnectionEvent, MessageEvent
from src.avails.exceptions import InvalidStateError
from src.avails.mixins import QueueMixIn, ReplyRegistryMixIn
from src.conduit import webpage
from src.core import bandwidth, peers
from src.core.app import App, ReadOnlyAppType, provide_app_ctx
from src.core.connector import Connector
from src.transfers import HEADERS

_logger = logging.getLogger(__name__)

_exit_stack = AsyncExitStack()
_msg_conn_pool = {}


async def initiate(app_ctx: App):
    data_dispatcher = MsgDispatcher()
    app_ctx.messages.dispatcher = data_dispatcher
    data_dispatcher.register_handler(HEADERS.CMD_TEXT, MessageHandler())
    msg_conn_handler = MessageConnHandler(app_ctx.read_only())
    app_ctx.connections.dispatcher.register_handler(HEADERS.CMD_MSG_CONN, msg_conn_handler)
    app_ctx.connections.dispatcher.register_handler(HEADERS.PING, PingHandler(app_ctx.read_only()))
    await app_ctx.exit_stack.enter_async_context(data_dispatcher)
    await app_ctx.exit_stack.enter_async_context(_exit_stack)


def MessageHandler():
    async def handler(event: MessageEvent):
        await webpage.msg_arrived(
            event.msg.header,
            event.msg["message"],
            event.msg.peer_id
        )

    return handler


class MsgDispatcher(QueueMixIn, ReplyRegistryMixIn, BaseDispatcher):
    """
    Works with ProcessDataHandler that sends any events into StreamDataDispatcher
    which dispatches event into respective handlers
    """
    __slots__ = ()

    async def submit(self, event: MessageEvent):
        self.msg_arrived(event.msg)
        message_header = event.msg.header
        try:
            handler = self.registry[message_header]
        except KeyError:
            _logger.warning(f"No handler found for {message_header}")
            return

        _logger.debug(f"dispatching msg with header {message_header} to {handler}")

        r = handler(event)
        if not isawaitable(r):
            return

        try:
            await asyncio.wait_for(r, const.TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK)
        except TimeoutError:
            _logger.debug(f"timeout at message processing task, cancelling {handler} task")
        except Exception as exp:
            _logger.error(f"{handler=}, failed with error", exc_info=exp)


def MessageConnHandler(app_ctx):
    """
    Iterates over a tcp stream
    if some data event occurs then calls data_dispatcher and submits that event

    Args:
        app_ctx(ReadOnlyAppType): application context
    """
    limiter = asyncio.Semaphore(const.MAX_CONCURRENT_MSG_PROCESSING)

    async def process_once(msg_connection):
        async with limiter:
            try:
                wire_data = await asyncio.wait_for(msg_connection.recv, const.MSG_RECV_TIMEOUT)
                print(f"[STREAM DATA] new msg {wire_data}")  # debug
                data_event = MessageEvent(wire_data, msg_connection)
            except InvalidPacket:
                pass

            await app_ctx.messages.dispatcher(data_event)

    async def handler(event: ConnectionEvent):
        finalizer = app_ctx.finalizing.is_set
        patience_threshold = 10
        counter = 0
        async with event.connection:
            msg_conn = MsgConnection(event.connection)
            _msg_conn_pool[event.connection.peer] = event.connection

            while finalizer():
                try:
                    await process_once(msg_conn)
                except TimeoutError:
                    counter += 1
                    if counter > patience_threshold:
                        _logger.debug(f"message processing threshold reached, returning {event.connection=}")
                        break

    return handler


def PingHandler(app_ctx):
    async def handler(msg_event: MessageEvent):
        ping = msg_event.msg
        un_ping = WireData(
            header=HEADERS.UNPING,
            peer_id=app_ctx.this_peer_id,
            msg_id=ping.msg_id,
        )
        return await msg_event.connection.send(un_ping)

    return handler


@asynccontextmanager
@provide_app_ctx
async def get_msg_conn(peer: RemotePeer, *, app_ctx=None):
    if peer not in _msg_conn_pool:
        connector = Connector()
        connection = await _exit_stack.enter_async_context(connector.connect(peer))
        await Wire.send_msg(
            connection,
            WireData(
                header=HEADERS.CMD_MSG_CONN,
                peer_id=app_ctx.this_peer_id
            )
        )
        msg_connection = MsgConnectionNoRecv(connection)
        _msg_conn_pool[peer] = msg_connection
        yield msg_connection
        return

    watcher = bandwidth.Watcher()
    connection = _msg_conn_pool.get(peer)
    active, _ = await watcher.refresh(peer, _msg_conn_pool.get(peer))

    if connection not in active:
        _msg_conn_pool.pop(peer)
    else:
        yield connection
        return

    async with get_msg_conn(peer) as msg_conn:
        yield msg_conn


class MsgSender:
    _message_senders = {}

    __slots__ = "peer", "_msg_queue", "_connection", "_connected", "_started", "_sender_task", "_finalized"

    def __init__(self, peer_obj):
        self.peer: RemotePeer = peer_obj
        self._msg_queue = asyncio.Queue()
        self._connection = None
        self._connected = asyncio.Event()
        self._message_senders[peer_obj.peer_id] = self
        self._started = False
        self._sender_task = None
        self._finalized = False

    async def connect(self):
        async with get_msg_conn(self.peer) as connection:
            self._connection = connection

        self._connected.set()

    async def _message_sender(self):
        self._started = True
        fut = None
        try:
            while True:
                message, fut = await self._msg_queue.get()
                if message is None:
                    return

                await self._connection.send(message)
                if not fut.done():
                    fut.set_result(message)

        except OSError as oe:
            if fut and not fut.done():
                fut.set_exception(oe)
            raise

    async def _sender_manager(self):
        while True:
            try:
                await self._message_sender()
                break  # if it's smooth exit, then we are done
            except OSError:
                self._connected.clear()
                await self._retry_connecting()
                if not self.peer.is_online:
                    await self.stop()
                    break

    async def _retry_connecting(self):
        async for timeout in use.get_timeouts(max_retries=-1):
            try:
                if self._connected.is_set():
                    return
                await self.connect()
                if not self.peer.is_online:
                    break
            except OSError:
                await webpage.failed_to_reach(self.peer.peer_id)
                await asyncio.sleep(timeout)

    async def send(self, msg):
        if self._started is False:
            raise InvalidStateError("sender not started yet!")

        loop = asyncio.get_event_loop()
        await self._msg_queue.put((msg, fut := loop.create_future()))
        return await fut

    @classmethod
    def get_sender(cls, peer_id):
        return cls._message_senders.get(peer_id, None)

    @property
    def is_connected(self):
        return self._connected.is_set()

    async def __aenter__(self):
        self._sender_task = asyncio.create_task(self._sender_manager(), name=f"message-sender-{self.peer.ip}")

    async def stop(self):
        self._message_senders.pop(self.peer.peer_id)

        self._msg_queue.put_nowait(None)
        await asyncio.sleep(0)
        await use.safe_cancel_task(self._sender_task)

        if not self._msg_queue.empty():
            _logger.warning(f"message queue not empty, discarding buffer {self._msg_queue}")

        self._connected.clear()
        self._connection = None
        self._finalized = True

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._finalized:
            return
        await self.stop()

    def __repr__(self):
        return f"<MsgSender(peer={self.peer}, connected={self.is_connected}, queued={self._msg_queue.qsize()})>"


async def connect_ahead(peer_id):
    if sender := MsgSender.get_sender(peer_id):
        if sender.peer.is_online and sender.is_connected:
            _logger.debug(f"not connecting again, already connected: {sender=!r}")
            return

    peer_obj = await peers.get_remote_peer(peer_id)
    _logger.info(f"connecting {peer_obj} for messages")
    sender = MsgSender(peer_obj)
    try:
        await sender.connect()
    except OSError:
        await sender.stop()
        _logger.debug(f"failed to connect {peer_obj}, initiating a connectivity check")
        return False

    await _exit_stack.enter_async_context(sender)
    return True


async def send_message(msg, peer_id):
    """Sends message to peer

    Args:
        msg(str): message to send
        peer_id(str): peer id to send to
    """

    if sender := MsgSender.get_sender(peer_id):
        _logger.debug(f"found msg sender for {peer_id}, sending message")
        await sender.send(msg.encode())
        return

    await connect_ahead(peer_id)
    await send_message(msg, peer_id)
