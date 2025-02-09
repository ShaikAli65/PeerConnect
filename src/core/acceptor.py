"""
Closely coupled with core.connector
Works with accepting incoming connections
lazy loading is used to avoid circular import through initiate_acceptor function
"""

import asyncio
import logging
import threading
from asyncio import TaskGroup
from collections import defaultdict
from contextlib import AsyncExitStack
from inspect import isawaitable
from types import ModuleType
from typing import Callable, Optional, TYPE_CHECKING

from src.avails import (BaseDispatcher, InvalidPacket, Wire, WireData, connect,
                        const, use)
from src.avails.connect import Connection
from src.avails.constants import MAX_CONCURRENT_MSG_PROCESSING
from src.avails.events import ConnectionEvent, StreamDataEvent
from src.avails.mixins import QueueMixIn, singleton_mixin
from src.core import DISPATCHS, Dock, peers
from src.managers.directorymanager import DirConnectionHandler
from src.managers.filemanager import FileConnectionHandler, OTMConnectionHandler
from src.transfers import HEADERS
from src.webpage_handlers import pagehandle

connector = None  # this is a global reference to lazy imported core.connector to avoid circular imports

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


async def initiate_acceptor():
    connection_dispatcher = ConnectionDispatcher(None, Dock.finalizing.is_set)
    data_dispatcher = StreamDataDispatcher(None, Dock.finalizing.is_set)

    data_handler = ProcessDataHandler(data_dispatcher, Dock.finalizing.is_set)

    data_dispatcher.register_handler(HEADERS.CMD_TEXT, pagehandle.MessageHandler())
    data_dispatcher.register_handler(HEADERS.CMD_CLOSING_HEADER, ConnectionCloseHandler())

    c_reg_handler = connection_dispatcher.register_handler
    c_reg_handler(HEADERS.CMD_FILE_CONN, FileConnectionHandler())
    c_reg_handler(HEADERS.CMD_RECV_DIR, DirConnectionHandler())
    c_reg_handler(HEADERS.OTM_UPDATE_STREAM_LINK, OTMConnectionHandler())
    c_reg_handler(HEADERS.CMD_BASIC_CONN, data_handler)

    Dock.dispatchers[DISPATCHS.CONNECTIONS] = connection_dispatcher
    Dock.dispatchers[DISPATCHS.STREAM_DATA] = data_dispatcher

    global connector
    import src.core.connector
    connector = src.core.connector
    acceptor = Acceptor(connection_disp=connection_dispatcher, finalizer=Dock.finalizing.is_set)

    # warning, careful with order
    await Dock.exit_stack.enter_async_context(data_dispatcher)
    await Dock.exit_stack.enter_async_context(connection_dispatcher)
    await Dock.exit_stack.enter_async_context(acceptor)

    await acceptor.initiate()


class ConnectionDispatcher(QueueMixIn, BaseDispatcher):
    __slots__ = ()

    async def submit(self, event: ConnectionEvent):
        handler = self.registry[event.handshake.header]
        _logger.info(f"dispatching connection with header {event.handshake.header} to {handler}")
        r = handler(event)

        if isawaitable(r):
            await r


class StreamDataDispatcher(QueueMixIn, BaseDispatcher):
    """
    Works with ProcessDataHandler that sends any events into StreamDataDispatcher
    which dispatches event into respective handlers

    """
    __slots__ = ()

    async def submit(self, event: StreamDataEvent):
        message_header = event.data.header
        handler = self.registry[message_header]

        _logger.info(f"[STREAM DATA] dispatching request with header {message_header} to {handler}")

        r = handler(event)

        if isawaitable(r):
            await r


def ProcessDataHandler(data_dispatcher, finalizer: Callable[[], bool]):
    """
    Iterates over a tcp stream
    if some data event occurs then calls data_dispatcher and submits that event

    Args:
        data_dispatcher(StreamDataDispatcher): any callable that reacts to event
        finalizer(Callable[[], bool]): a flag to check while looping, should return False to stop loop

    """
    limiter = asyncio.Semaphore(MAX_CONCURRENT_MSG_PROCESSING)

    async def process_once(event):
        async with limiter:
            raw_data_len = await use.recv_int(event.connection.recv)
            if raw_data_len <= 0:
                return

            raw_data = await event.connection.recv(raw_data_len)
            data = WireData.load_from(raw_data)
            print(f"[STREAM DATA] new data {data}")  # debug
            data_event = StreamDataEvent(data, event.connection)
            await asyncio.wait_for(data_dispatcher(data_event), const.TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK)

    async def handler(event: ConnectionEvent):
        with event.connection:
            while finalizer():
                await process_once(event)

    return handler


def ConnectionCloseHandler():
    async def handler(event: StreamDataEvent):
        event.connection.socket.close()

    return handler


@singleton_mixin
class Acceptor:
    __annotations__ = {
        'address': tuple,
        '__control_flag': threading.Event,
        'main_socket': connect.Socket,
        'stopping': asyncio.Event,
        'currently_in_connection': defaultdict,
        'RecentConnections': ModuleType,
        '__loop': asyncio.AbstractEventLoop,
    }

    current_connections = {}

    def __init__(self, connection_disp, finalizer, ip=None, port=None):
        self._exit_stack = AsyncExitStack()
        self.address = (ip or const.THIS_IP, port or const.PORT_THIS)
        self.stopping = finalizer
        self.main_socket: Optional[connect.Socket] = None
        self.back_log = 4
        self.currently_in_connection = defaultdict(int)
        self.max_timeout = 90
        _logger.info(f"Initiating Acceptor {self.address}")
        self.connection_dispatcher = connection_disp

    async def initiate(self):

        with await self._start_socket() as self.main_socket:
            _logger.info("Listening for connections")
            async with TaskGroup() as tg:
                while not self.stopping():
                    try:
                        initial_conn, addr = await self.main_socket.aaccept()
                    except OSError:
                        if self.stopping():
                            # if we are finalizing then
                            # it's mostly a case for asyncio cancelling this task

                            # but,
                            # async def accept_coro(future, conn):
                            #   Coroutine closing the accept socket if the future is cancelled
                            #   try:
                            #       await future
                            #   except exceptions.CancelledError:
                            #       conn.close()
                            #       raise
                            #
                            # this part of asyncio internals does not handle OSError,
                            # causing a dirty log
                            #
                            # Task exception was never retrieved
                            # future: < Task finished name = 'Task-6' coro = accept_coro() done,.. >
                            # OSError: [WinError 995] The I/O operation has been aborted ...

                            # try dealing with this
                            return
                        raise

                    tg.create_task(
                        self.__accept_connection(initial_conn),
                        name=f"acceptor task for socket address: {addr}"
                    )
                    _logger.info(f"New connection from {addr}")
                    await asyncio.sleep(0)

    async def _start_socket(self):

        try:
            addr_info = await anext(use.get_addr_info(*self.address, family=const.IP_VERSION))
        except StopAsyncIteration:
            raise RuntimeError("No valid address found for the server")
        except Exception as e:
            _logger.error(f"Error resolving address: {e}", exc_info=True)
            raise

        sock_family, sock_type, _, _, address = addr_info
        sock = const.PROTOCOL.create_async_server_sock(
            asyncio.get_running_loop(),
            address,
            family=const.IP_VERSION,
            backlog=self.back_log
        )
        return sock

    async def __accept_connection(self, initial_conn):
        handshake = await self._perform_handshake(initial_conn)
        if not handshake:
            return
        peer = await peers.get_remote_peer_at_every_cost(handshake.peer_id)
        conn = Connection.create_from(initial_conn, peer)
        self._exit_stack.enter_context(initial_conn)
        con_event = ConnectionEvent(conn, handshake)
        self.connection_dispatcher(con_event)

    @classmethod
    async def _perform_handshake(cls, initial_conn):
        try:
            raw_hand_shake = await asyncio.wait_for(
                Wire.receive_async(initial_conn), const.SERVER_TIMEOUT
            )
            if raw_hand_shake:
                return WireData.load_from(raw_hand_shake)
        except TimeoutError:
            _logger.error(f"new connection inactive for {const.SERVER_TIMEOUT}s, closing")
            initial_conn.close()
        except OSError:
            _logger.error(f"Socket error", exc_info=True)
            initial_conn.close()
        except InvalidPacket:
            _logger.error(f"Initial handshake packet is invalid, closing connection {raw_hand_shake=}", exc_info=True)
            initial_conn.close()
        return None

    async def reset_socket(self):
        self.main_socket.close()
        self.main_socket = await self._start_socket()

    def end(self):
        self.main_socket.close()

    async def __aenter__(self):
        await self._exit_stack.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._exit_stack.__aexit__(exc_tb, exc_type, exc_tb)
        self.end()

    def __del__(self):
        self.end()

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'
