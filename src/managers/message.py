import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from inspect import isawaitable

from src.avails import BaseDispatcher, InvalidPacket, RemotePeer, Wire, WireData
from src.avails.connect import MsgConnection
from src.avails.constants import MAX_CONCURRENT_MSG_PROCESSING, TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK
from src.avails.events import ConnectionEvent, MessageEvent
from src.avails.mixins import QueueMixIn, ReplyRegistryMixIn
from src.conduit import pagehandle
from src.core import bandwidth
from src.core.connector import Connector
from src.core.public import DISPATCHS, Dock, connections_dispatcher, get_this_remote_peer
from src.transfers import HEADERS

_logger = logging.getLogger(__name__)

_locks_stack = AsyncExitStack()
_msg_conn_pool = {}


async def initiate(exit_stack, dispatchers, finalizing):
    data_dispatcher = MsgDispatcher()
    data_dispatcher.register_handler(HEADERS.CMD_TEXT, pagehandle.MessageHandler())
    dispatchers[DISPATCHS.MESSAGES] = data_dispatcher
    msg_conn_handler = MessageConnHandler(data_dispatcher, finalizing.is_set)
    connections_dispatcher().register_handler(HEADERS.CMD_MSG_CONN, msg_conn_handler)
    connections_dispatcher().register_handler(HEADERS.PING, PingHandler())
    await exit_stack.enter_async_context(data_dispatcher)
    await exit_stack.enter_async_context(_locks_stack)
    return data_dispatcher


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
            _logger.error(f"No handler found for {message_header}")
            return

        _logger.info(f"dispatching msg with header {message_header} to {handler}")

        r = handler(event)

        if isawaitable(r):
            await r


def MessageConnHandler(data_dispatcher, finalizer):
    """
    Iterates over a tcp stream
    if some data event occurs then calls data_dispatcher and submits that event

    Args:
        data_dispatcher(MsgDispatcher): any callable that reacts to event
        finalizer(Callable[[], bool]): a flag to check while looping, should return False to stop loop

    """
    limiter = asyncio.Semaphore(MAX_CONCURRENT_MSG_PROCESSING)

    async def process_once(msg_connection):
        async with limiter:
            try:
                wire_data = msg_connection.recv()
                print(f"[STREAM DATA] new msg {wire_data}")  # debug
                data_event = MessageEvent(wire_data, msg_connection)
            except InvalidPacket:
                pass

            await asyncio.wait_for(data_dispatcher(data_event), TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK)

    async def handler(event: ConnectionEvent):
        with event.connection:
            msg_conn = MsgConnection(event.connection)
            _msg_conn_pool[event.connection.peer] = event.connection

            while finalizer():
                await process_once(msg_conn)

    return handler


def PingHandler():
    async def handler(msg_event: MessageEvent):
        ping = msg_event.msg
        un_ping = WireData(
            header=HEADERS.UNPING,
            peer_id=get_this_remote_peer().peer_id,
            msg_id=ping.msg_id,
        )
        return await msg_event.connection.send(un_ping)

    return handler


async def recv(*args):
    raise NotImplemented("not allowed to recv using msg connection")


@asynccontextmanager
async def get_msg_conn(peer: RemotePeer):
    if peer not in _msg_conn_pool:
        connector = Connector()
        connection = await _locks_stack.enter_async_context(connector.connect(peer))
        await Wire.send_msg(
            connection,
            WireData(
                header=HEADERS.CMD_MSG_CONN,
                peer_id=get_this_remote_peer().peer_id
            )
        )
        msg_connection = MsgConnection(connection)
        _msg_conn_pool[peer] = msg_connection
        msg_connection.recv = recv  # receiving through message connection is not allowed for now
        yield msg_connection
    else:
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


async def send_message(msg, peer, *, expect_reply=False):
    """Sends message to peer

    Args:
        peer(RemotePeer): peer to send to
        msg(WireData): message to send
        expect_reply: if true then waits until a reply

    Returns:

    """
    async with get_msg_conn(peer) as connection:
        await connection.send(msg)
