import asyncio
import functools
import logging
import socket
import textwrap
import threading
from asyncio import TaskGroup
from collections import defaultdict
from inspect import isawaitable
from types import ModuleType
from typing import Optional

from src.avails import (BaseDispatcher, QueueMixIn, RemotePeer, SocketStore, Wire, WireData, connect, const, use)
from src.avails.events import ConnectionEvent, StreamDataEvent
from src.core import DISPATCHS, Dock, get_this_remote_peer
from src.core.transfers import HEADERS
from src.core.transfers.transports import StreamTransport
from src.core.webpage_handlers import pagehandle
from src.managers.filemanager import FileConnectionHandler, OTMConnectionHandler
from src.managers.directorymanager import DirConnectionHandler
_logger = logging.getLogger(__name__)


async def initiate_connections():
    acceptor = Acceptor()
    acceptor.data_dispatcher.register_handler(
        HEADERS.CMD_TEXT,
        pagehandle.MessageHandler()
    )

    Dock.dispatchers[DISPATCHS.CONNECTIONS] = acceptor.connection_dispatcher
    Dock.dispatchers[DISPATCHS.STREAM_DATA] = acceptor.data_dispatcher

    acceptor.connection_dispatcher.register_handler(HEADERS.CMD_FILE_CONN, FileConnectionHandler())
    acceptor.connection_dispatcher.register_handler(HEADERS.CMD_RECV_DIR, DirConnectionHandler())
    acceptor.connection_dispatcher.register_handler(HEADERS.CMD_CLOSING_HEADER, ConnectionCloseHandler())
    acceptor.connection_dispatcher.register_handler(HEADERS.OTM_UPDATE_STREAM_LINK, OTMConnectionHandler())
    # acceptor.connection_dispatcher.register_handler(HEADERS.GOSSIP_UPDATE_STREAM_LINK)
    await acceptor.initiate()


class ConnectionDispatcher(QueueMixIn, BaseDispatcher):
    async def submit(self, event: ConnectionEvent):
        handler = self.registry[event.handshake.header]
        _logger.info(f"[CONNECTIONS] dispatching connection with header {event.handshake.header} to {handler}")
        r = handler(event)

        if isawaitable(r):
            await r


class StreamDataDispatcher(QueueMixIn, BaseDispatcher):
    async def submit(self, event: StreamDataEvent):
        message_header = event.data.header
        handler = self.registry[message_header]

        _logger.info(f"[STREAM DATA] dispatching request with header {message_header} to {handler}")

        r = handler(event)

        if isawaitable(r):
            await r


def ProcessDataHandler(data_dispatcher: StreamDataDispatcher, finalizer):
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


def ConnectionCloseHandler():
    async def handler(event: StreamDataEvent):
        event.transport.socket.close()
        Dock.connected_peers.remove_and_close(event.data.peer_id)

    return handler


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

    _instance = None
    _initialized = False
    current_socks = SocketStore()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Acceptor, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, ip=None, port=None):
        if self._initialized is True:
            return
        self.address = (ip or const.THIS_IP, port or const.PORT_THIS)
        self.stopping = Dock.finalizing.is_set
        self.main_socket: Optional[connect.Socket] = None
        self.back_log = 4
        self.currently_in_connection = defaultdict(int)
        self.__loop = asyncio.get_running_loop()
        self.all_tasks = set()
        self.max_timeout = 90
        _logger.info("[ACCEPTOR] ::Initiating Acceptor ", extra={'addr': self.address})
        self._initialized = True
        self._spawn_task = functools.partial(use.spawn_task, bookeep=self.all_tasks.add,
                                             done_callback=lambda t: self.all_tasks.remove(t))

        self.connection_dispatcher = ConnectionDispatcher(None, Dock.finalizing.is_set)
        self.data_dispatcher = StreamDataDispatcher(None, Dock.finalizing.is_set)
        data_handler = ProcessDataHandler(self.data_dispatcher, Dock.finalizing.is_set)
        self.connection_dispatcher.register_handler(HEADERS.CMD_VERIFY_HEADER, data_handler)

    async def initiate(self):
        self.connection_dispatcher.transport = self.main_socket
        with await self._start_socket() as self.main_socket:
            _logger.info("[ACCEPTOR] ::Listening for connections")
            async with TaskGroup() as tg:
                while not self.stopping():
                    initial_conn, addr = await self.main_socket.aaccept()
                    _logger.debug(f"[ACCEPTOR] New connection from {addr}")
                    tg.create_task(self.__accept_connection(initial_conn))
                    await asyncio.sleep(0)

    async def _start_socket(self):
        addr_info = await self.__loop.getaddrinfo(*self.address, family=const.IP_VERSION)
        sock_family, sock_type, _, _, address = addr_info[0]
        sock = const.PROTOCOL.create_async_server_sock(
            self.__loop,
            address,
            family=const.IP_VERSION,
            backlog=self.back_log
        )
        return sock

    async def __accept_connection(self, initial_conn):
        transport = StreamTransport(initial_conn)

        try:
            raw_hand_shake = await transport.recv()
        except (socket.error, OSError) as e:
            # error_log(f"Socket error: at {use.func_str(self.__accept_connection)} exp:{e}")
            _logger.error(f"[ACCEPTOR] Socket error", exc_info=e)
            initial_conn.close()
            return

        hand_shake = WireData.load_from(raw_hand_shake)
        con_event = ConnectionEvent(transport, hand_shake)
        self.connection_dispatcher(con_event)
        Dock.connected_peers.add_peer_sock(hand_shake.peer_id, initial_conn)

    async def reset_socket(self):
        self.main_socket.close()
        self.main_socket = await self._start_socket()

    def end(self):
        self.main_socket.close()
        self.stopping = True
        current_connections = Dock.connected_peers.socket_cache
        for connection in current_connections.values():
            connection.close()

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
        _logger.info(
            ("[CONNECTIONS] cache miss --current :",
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
        _logger.info(f"[CONNECTIONS] Sent verification to {connection_socket.getpeername()}")  # debug
        return True
