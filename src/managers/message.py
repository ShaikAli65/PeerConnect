import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from inspect import isawaitable

from src.avails import BaseDispatcher, InvalidPacket, RemotePeer
from src.avails.connect import MsgConnection
from src.avails.constants import MAX_CONCURRENT_MSG_PROCESSING, TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK
from src.avails.events import ConnectionEvent, StreamDataEvent
from src.avails.mixins import QueueMixIn
from src.core import DISPATCHS, Dock, connections_dispatcher
from src.core.connector import Connector
from src.transfers import HEADERS
from src.webpage_handlers import pagehandle

_logger = logging.getLogger(__name__)

_locks_stack = AsyncExitStack()
_msg_conn_pool = {}


async def initiate():
    data_dispatcher = MsgDispatcher(None, Dock.finalizing.is_set)
    data_dispatcher.register_handler(HEADERS.CMD_TEXT, pagehandle.MessageHandler())
    Dock.dispatchers[DISPATCHS.MESSAGES] = data_dispatcher
    msg_conn_handler = MessageConnHandler(data_dispatcher, Dock.finalizing.is_set)
    connections_dispatcher().register_handler(HEADERS.CMD_MSG_CONN, msg_conn_handler)
    await Dock.exit_stack.enter_async_context(data_dispatcher)
    await Dock.exit_stack.enter_async_context(_locks_stack)
    return data_dispatcher


class MsgDispatcher(QueueMixIn, BaseDispatcher):
    """
    Works with ProcessDataHandler that sends any events into StreamDataDispatcher
    which dispatches event into respective handlers
    """
    __slots__ = ()

    async def submit(self, event: StreamDataEvent):
        message_header = event.data.header
        handler = self.registry[message_header]

        _logger.info(f"[STREAM DATA] dispatching msg with header {message_header} to {handler}")

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
                data_event = StreamDataEvent(wire_data, msg_connection)
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


@asynccontextmanager
async def get_msg_conn(peer: RemotePeer):
    if peer not in _msg_conn_pool:
        connector = Connector()
        connection = await _locks_stack.enter_async_context(connector.connect(peer))
        msg_connection = MsgConnection(connection)
        _msg_conn_pool[peer] = msg_connection
        yield msg_connection


def send_message(peer, msg):
    ...
