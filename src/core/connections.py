import asyncio
import socket
import textwrap
import threading
from collections import defaultdict
from types import ModuleType
from typing import Optional

from src.avails import (RemotePeer, SocketStore, Wire, WireData, connect, const, use)
from . import Dock, get_this_remote_peer
from .transfers import HEADERS
from .webpage_handlers import pagehandle
from ..managers import directorymanager, filemanager, gossip_manager


async def initiate_connections():
    acceptor = Acceptor()
    await acceptor.initiate()


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
        self.stopping = False
        self.main_socket: Optional[connect.Socket] = None
        self.back_log = 4
        self.currently_in_connection = defaultdict(int)
        self.__loop = asyncio.get_running_loop()
        self.all_tasks = set()
        self.max_timeout = 90
        use.echo_print("::Initiating Acceptor ", self.address)
        self._initialized = True

    def set_loop(self, loop):
        self.__loop = loop

    async def initiate(self):
        self.main_socket = await self.start_socket()
        use.echo_print("::Listening for connections", self.main_socket)
        # initial_backoff = use.get_timeouts()
        with self.main_socket:
            while not self.stopping:
                initial_conn, _ = await self.main_socket.aaccept()
                use.echo_print(f"New connection from {_}", initial_conn)
                f = use.wrap_with_tryexcept(self.__accept_connection, initial_conn)
                task = asyncio.create_task(f)
                task.add_done_callback(lambda t: self.all_tasks.discard(t))
                self.all_tasks.add(task)
                await asyncio.sleep(0)

    async def start_socket(self):
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
        try:
            peer_id = await self.verify(initial_conn)
            if not peer_id:
                return
            Dock.connected_peers.add_peer_sock(peer_id, initial_conn)
            await self.handle_peer(peer_id)
        except (socket.error, OSError) as e:
            # error_log(f"Socket error: at {use.func_str(self.__accept_connection)} exp:{e}")
            use.echo_print(f"Socket error: at {use.func_str(self.__accept_connection)} exp:{e}")  # debug
            initial_conn.close()

    async def verify(self, connection):
        """
        :param connection: connection from peer
        :returns peer_id: if verification is successful else None (implying socket to be removed)
        """
        data = await Wire.receive_async(connection)
        hand_shake = WireData.load_from(data)
        if hand_shake.match_header(HEADERS.CMD_VERIFY_HEADER):
            peer_id = hand_shake.id
            self.currently_in_connection[peer_id] += 1
            use.echo_print("verified peer", peer_id)  # debug
            return peer_id
        if hand_shake.match_header(HEADERS.CMD_FILE_CONN):
            return filemanager.file_recv_request_connection_arrived(connection, hand_shake)

        if hand_shake.match_header(HEADERS.GOSSIP_UPDATE_STREAM_LINK):
            use.echo_print("got a gossip stream link connection request delegating to gossip manager", connection)  # debug
            return gossip_manager.update_gossip_stream_socket(connection, hand_shake)

    async def handle_peer(self, peer_id):
        sock = Dock.connected_peers.get_socket(peer_id)
        while self.currently_in_connection[peer_id]:
            try:
                raw_data = await Wire.receive_async(sock)
                data = WireData.load_from(raw_data)
                print("new data arrived", data)  # debug
                self.__process_data(data)
            except TypeError as tp:
                print("got type error possible data illformed", tp)

    @staticmethod
    def __process_data(data: WireData):
        if data.match_header(HEADERS.CMD_TEXT):
            pagehandle.new_message_arrived(data)
        elif data.match_header(HEADERS.CMD_RECV_FILE):
            directorymanager.new_directory_transfer_request(data)
        elif data.match_header(HEADERS.CMD_CLOSING_HEADER):
            directorymanager.new_directory_transfer_request(data)

    async def reset_socket(self):
        self.main_socket.close()
        self.main_socket = await self.start_socket()

    def end(self):
        self.main_socket.close()
        self.stopping = True
        current_connections = self.currently_in_connection
        for peer in current_connections:
            current_connections[peer] = 0

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'


class Connector:
    _current_connected = connect.Socket()
    # :todo: make this more advanced such that it can handle mulitple requests related to same socket

    @classmethod
    async def get_connection(cls, peer_obj: RemotePeer) -> connect.Socket:
        use.echo_print('a connection request made to :', peer_obj.uri)  # debug
        if sock := Dock.connected_peers.is_connected(peer_obj.id):
            pr_str = f"cache hit !{textwrap.fill(peer_obj.username, width=10)} and socket is connected"
            use.echo_print(pr_str, sock.getpeername())  # debug
            cls._current_connected = sock
            return sock
        del sock
        peer_sock = await cls._add_connection(peer_obj)
        await cls._verifier(peer_sock)
        use.echo_print(
            "cache miss --current :",
            textwrap.fill(peer_obj.username, width=10),
            peer_sock.getpeername()[:2],
            peer_sock.getsockname()[:2]
        )  # debug
        Dock.connected_peers.add_peer_sock(peer_obj.id, peer_sock)
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
            _id=get_this_remote_peer().id,
        )
        await Wire.send_async(connection_socket, bytes(verification_data))
        use.echo_print("Sent verification to ", connection_socket.getpeername())  # debug
        return True
