import asyncio
import logging
import textwrap
import threading
from asyncio import TaskGroup
from collections import defaultdict
from contextlib import AsyncExitStack
from inspect import isawaitable
from types import ModuleType
from typing import Callable, Optional

from src.avails import (BaseDispatcher, InvalidPacket, RemotePeer, SocketCache, SocketStore, Wire, WireData, connect,
                        const, use)
from src.avails.events import ConnectionEvent, StreamDataEvent
from src.avails.mixins import QueueMixIn, singleton_mixin
from src.core import DISPATCHS, Dock, get_this_remote_peer
from src.managers.directorymanager import DirConnectionHandler
from src.managers.filemanager import FileConnectionHandler, OTMConnectionHandler
from src.transfers import HEADERS
from src.transfers.transports import StreamTransport
from src.webpage_handlers import pagehandle

_logger = logging.getLogger(__name__)


async def initiate_connections():
    acceptor = Acceptor(finalizer=Dock.finalizing.is_set, connected_peers=Dock.connected_peers)
    await Dock.exit_stack.enter_async_context(acceptor)
    acceptor.data_dispatcher.register_handler(
        HEADERS.CMD_TEXT,
        pagehandle.MessageHandler()
    )

    Dock.dispatchers[DISPATCHS.CONNECTIONS] = acceptor.connection_dispatcher
    Dock.dispatchers[DISPATCHS.STREAM_DATA] = acceptor.data_dispatcher
    register_handler = acceptor.connection_dispatcher.register_handler

    register_handler(HEADERS.CMD_FILE_CONN, FileConnectionHandler())
    register_handler(HEADERS.CMD_RECV_DIR, DirConnectionHandler())
    register_handler(HEADERS.CMD_CLOSING_HEADER, ConnectionCloseHandler(Dock.connected_peers))
    register_handler(HEADERS.OTM_UPDATE_STREAM_LINK, OTMConnectionHandler())
    # acceptor.connection_dispatcher.register_handler(HEADERS.GOSSIP_UPDATE_STREAM_LINK)
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

    async def handler(event: ConnectionEvent):
        with event.transport.socket:
            stream_socket = event.transport
            while finalizer():
                raw_data = await stream_socket.recv()

                data = WireData.load_from(raw_data)

                _logger.info(f"[STREAM DATA] new data {data}")  # debug
                data_event = StreamDataEvent(data, stream_socket)
                data_dispatcher(data_event)

    return handler


def ConnectionCloseHandler(connected_peers: SocketCache):
    async def handler(event: StreamDataEvent):
        event.transport.socket.close()
        connected_peers.remove_and_close(event.data.peer_id)

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

    current_socks = SocketStore()

    def __init__(self, finalizer, connected_peers, ip=None, port=None):
        self._exit_stack = AsyncExitStack()
        self.address = (ip or const.THIS_IP, port or const.PORT_THIS)
        self.stopping = finalizer
        self.main_socket: Optional[connect.Socket] = None
        self.back_log = 4
        self.currently_in_connection = defaultdict(int)
        self.max_timeout = 90
        _logger.info(f"Initiating Acceptor {self.address}")
        self.connected_peers = connected_peers
        self.connection_dispatcher = ConnectionDispatcher(None, finalizer)
        self.data_dispatcher = StreamDataDispatcher(None, finalizer)
        data_handler = ProcessDataHandler(self.data_dispatcher, finalizer)
        self.connection_dispatcher.register_handler(HEADERS.CMD_VERIFY_HEADER, data_handler)

    async def initiate(self):
        self.connection_dispatcher.transport = self.main_socket
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
        transport = StreamTransport(initial_conn)
        handshake = await self._perform_handshake(initial_conn, transport)
        if not handshake:
            return

        self._exit_stack.enter_context(initial_conn)
        con_event = ConnectionEvent(transport, handshake)
        self.connection_dispatcher(con_event)
        self.connected_peers.add_peer_sock(handshake.peer_id, initial_conn)

    @classmethod
    async def _perform_handshake(cls, initial_conn, transport):
        try:
            raw_hand_shake = await asyncio.wait_for(transport.recv(), const.SERVER_TIMEOUT)
            return WireData.load_from(raw_hand_shake)
        except TimeoutError:
            _logger.error(f"new connection inactive for {const.SERVER_TIMEOUT}s, closing")
            initial_conn.close()
        except OSError:
            _logger.error(f"Socket error", exc_info=True)
            initial_conn.close()
        except InvalidPacket:
            _logger.error("Initial handshake packet is invalid, closing connection", exc_info=True)
            initial_conn.close()
        return None

    async def reset_socket(self):
        self.main_socket.close()
        self.main_socket = await self._start_socket()

    def end(self):
        self.main_socket.close()

    async def __aenter__(self):
        await self._exit_stack.__aenter__()
        await self._exit_stack.enter_async_context(self.data_dispatcher)
        await self._exit_stack.enter_async_context(self.connection_dispatcher)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._exit_stack.__aexit__(exc_tb, exc_type, exc_tb)
        self.end()

    def __del__(self):
        self.end()

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'


class Connector:
    _current_connected = connect.Socket()

    # :todo: make this more advanced such that it can handle multiple requests related to same socket

    @classmethod
    async def get_connection(cls, peer_obj: RemotePeer) -> connect.Socket:
        use.echo_print('a connection request made to :', peer_obj.uri)  # debug
        if sock := Dock.connected_peers.is_connected(peer_obj.peer_id):
            pr_str = (f"[CONNECTIONS] cache hit !{textwrap.fill(peer_obj.username, width=10)}"
                      f" and socket is connected"
                      f"{sock.getpeername()}")
            _logger.info(pr_str)
            cls._current_connected = sock
            return sock
        del sock
        peer_sock = await cls._add_connection(peer_obj)
        await cls._verifier(peer_sock)
        _logger.debug(
            ("cache miss --current :",
             f"{textwrap.fill(peer_obj.username, width=10)}",
             f"{peer_sock.getpeername()[:2]}",
             f"{peer_sock.getsockname()[:2]}")
        )
        Dock.connected_peers.add_peer_sock(peer_obj.peer_id, peer_sock)
        cls._current_connected = peer_sock
        # use.echo_print(f"handle signal to page, that we can't reach {peer_obj.username}, or he is offline")
        return peer_sock

    @classmethod
    async def _add_connection(cls, peer_obj: RemotePeer) -> connect.Socket:
        connection_socket = await connect.connect_to_peer(peer_obj, timeout=1, retries=3)
        Dock.connected_peers.add_peer_sock(peer_obj.id, connection_socket)
        return connection_socket

    @classmethod
    async def _verifier(cls, connection_socket):
        verification_data = WireData(
            header=HEADERS.CMD_VERIFY_HEADER,
            msg_id=get_this_remote_peer().peer_id,
        )
        await Wire.send_async(connection_socket, bytes(verification_data))
        _logger.info(f"Sent verification to {connection_socket.getpeername()}")  # debug
        return True
