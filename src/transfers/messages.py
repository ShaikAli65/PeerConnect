import asyncio
from typing import Awaitable, Callable, Self

from src.avails import RemotePeer, WireData, const, use
from src.avails.exceptions import FailedToSend, InvalidPacket, InvalidStateError
from src.core.app import ReadOnlyAppType
from src.net import MsgConnection, MsgConnectionNoRecv
from src.net.events import MessageEvent
from . import _logger
from ._headers import HEADERS

RegisterReplyCallable = Callable[[str], asyncio.Future]
ConnectorCallable = Callable[[RemotePeer], Awaitable[MsgConnectionNoRecv]]


class MsgSender:
    """Message Sender

    When an object is created, it gets added to an internal pool and can be accessed using
    `get_sender` method.

    Most simple function call chain to send a message can be::

        1. send call
        2. queues msg and get a registered ack future
        3. internal sender loop picks it up
        4. sends message
        5. other side acknowledges the received message and registered future gets set
        6. send call releases

    Call chain can be complicated (toggling between reconnects and message sending) when connections
    are getting broken up frequently

    Context manager needs to be entered to start sending, uses connector to connect peer,

    Retries connecting peer if connection returned by connector callable fails with OSError
    timeouts between each retry is reasonable.

        If the connect loop is sleeping on a timeout, one can force its waking up and start
    the message sending loop by calling `connect` method and if that connect method call is
    success, it wakes blocked msg sending loop.

    Note:
        Does not stop ```{retry+send-msg}``` loop until context manager is exited

    """
    _message_senders = {}

    __slots__ = (
        "peer",
        "_msg_queue",
        "_connection",
        "_connected",
        "_started",
        "_sender_task",
        "_ack_counter_part",
        "_connector",
        "__finalized",
    )

    def __init__(self, peer_obj, ack_counter_part: RegisterReplyCallable, connector: ConnectorCallable):
        """
        Args:
            peer_obj(RemotePeer): associated peer object
            ack_counter_part(RegisterReplyCallable):
                this should return a future that gets set when a reply arrives for the registered message id
            connector(ConnectorCallable): callable that connects to given peer_obj
        """

        self.peer: RemotePeer = peer_obj
        self._msg_queue = asyncio.Queue()
        self._connection = None
        self._connected = asyncio.Event()
        self._message_senders[peer_obj.peer_id] = self
        self._started = False
        self._sender_task = None
        self.__finalized = False
        self._ack_counter_part = ack_counter_part
        self._connector = connector

    async def connect(self):
        self._connection = await self._connector(self.peer)
        self._connected.set()
        _logger.debug("message sender connected")

    async def _message_sender(self):
        self._started = True
        message, fut = None, None
        try:
            while True:
                message, fut = await self._msg_queue.get()
                if message is None:
                    return

                await self._connection.send(bytes(message))
                _logger.debug(f"> sent, message={repr(message)[:30]}")

        except OSError as oe:
            if fut and not fut.done():
                fts = FailedToSend()
                fts.__cause__ = oe
                fts.item = message
                fut.set_exception(fts)
            _logger.debug(f"!> failed sending, message={repr(message)[:30]}")
            raise

    async def _sender_manager(self):
        try:
            while True:
                try:
                    await self._message_sender()
                    break  # if it's smooth exit, then we are done
                except OSError:
                    _logger.debug("~ changing message connection status to False")
                    self._connected.clear()
                    await self._retry_connecting()
        finally:
            _logger.debug("sender manager exiting...")
            await self.stop(cancel_sender=False)  # we are finalizing anyhow

    async def _retry_connecting(self):
        for timeout in use.get_timeouts(max_retries=const.CONNECTION_RETRIES):
            _logger.debug(f"> retrying connecting to, peer={self.peer.peer_id}")
            try:
                if self.is_connected:
                    return
                await self.connect()
                _logger.debug(f"# peer connected for messaging, peer={self.peer.peer_id}")
                _logger.debug(f"# changing message sender status to connected, {self.peer.peer_id}")
            except OSError:
                _logger.debug(f"> failed connecting to, peer={self.peer.peer_id}")
                waits = (asyncio.ensure_future(x) for x in (self._connected.wait(), asyncio.sleep(timeout)))
                await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)

    async def send(self, msg):
        """Send Message

        Queues message and waits on a future that can be:
            1. to get an ack in response to message sent
            2. to get an error (i.e. OSError) indicating failure to send message

        Callers can check for OSError or keep a reasonable timeout on this function call

        Args:
              msg(WireData): message to send, should have a unique id
        Raises:
            InvalidStateError: if sender is not started yet
            InvalidPacket: is message does not have an id
        """

        if self._started is False:
            raise InvalidStateError("sender not started yet!")

        if msg.msg_id is None:
            raise InvalidPacket("expecting a `msg` with some unique id")
        _logger.debug(f">! queueing message packet for, peer={self.peer}")
        await self._msg_queue.put((
            msg,
            fut := self._ack_counter_part(msg.msg_id)
            # register a reply ack
        ))
        r = await fut
        _logger.debug(f"< received ack for {msg.msg_id=}, from peer_addr={self.peer.uri}")
        return r

    @classmethod
    def get_sender(cls, peer_id) -> Self:
        return cls._message_senders.get(peer_id, None)

    async def stop(self, cancel_sender=True):
        if self.__finalized:
            return

        # only remove the object inside pool is still `self`
        if (this := self.get_sender(self.peer.peer_id)) and this is self:
            self._message_senders.pop(self.peer.peer_id)

        if cancel_sender:
            self._msg_queue.put_nowait([None] * 2)
            await asyncio.sleep(0)
            if self._sender_task is not None:
                await use.safe_cancel_task(self._sender_task)

        if self._msg_queue.empty():
            _logger.warning(f"!# message queue not empty, discarding buffer {self._msg_queue}")

        self._connected.clear()
        self._connection = None
        self.__finalized = True
        _logger.debug(f"stopped message sender for peer={self.peer}")

    @property
    def is_connected(self):
        return self._connected.is_set()

    async def __aenter__(self):
        _logger.debug(f"starting sender loop for peer={self.peer}")
        self._sender_task = asyncio.create_task(self._sender_manager(), name=f"message-sender-{self.peer.ip}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def __repr__(self):
        return f"<MsgSender(peer={self.peer}, connected={self.is_connected}, queued={self._msg_queue.qsize()})>"


class MsgReceiver:
    def __init__(self, app_ctx: ReadOnlyAppType, msg_conn: MsgConnection):
        self.app_ctx = app_ctx
        self.limiter = asyncio.Semaphore(const.MAX_CONCURRENT_MSG_PROCESSING)
        self.msg_conn = msg_conn

    async def _process_once(self, msg_connection: MsgConnection, msg_dispatcher):
        async with self.limiter:
            try:
                wire_data = await msg_connection.recv()
                _logger.debug(f"< new msg {wire_data}")
            except InvalidPacket:
                _logger.info(f"<! malformed packet", exc_info=True)
                return

            # optimize ack processing by quickly returning without spawning a task
            if wire_data.header == HEADERS.MSG_ACK:
                if msg_dispatcher.is_registered(wire_data):
                    msg_dispatcher.reply_arrived(wire_data)
                return

            data_event = MessageEvent(wire_data, msg_connection)
            await msg_dispatcher(data_event)
            ack = WireData(header=HEADERS.MSG_ACK, msg_id=wire_data.msg_id)
            await msg_connection.send(ack)
            _logger.debug(f"> sent ack for {wire_data.msg_id=}")

    async def start_receiving(self):
        finalized = self.app_ctx.finalizing.is_set
        patience_threshold = 10
        counter = 0
        msg_conn = self.msg_conn
        msg_dispatcher = self.app_ctx.messages.dispatcher
        process_once = self._process_once

        while not finalized():
            try:
                await process_once(msg_conn, msg_dispatcher)
            except TimeoutError:
                counter += 1
                if counter > patience_threshold:
                    _logger.debug(f"message processing threshold reached, returning {self.msg_conn=}")
                    break
            except OSError:
                _logger.debug(f"connection to:{msg_conn.peer}, failed", exc_info=True)
                raise
