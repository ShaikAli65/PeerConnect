import asyncio
import socket
import textwrap
import threading
from collections import defaultdict
from types import ModuleType
from typing import Optional

# from . import connected_peers
from . import get_this_remote_peer, Dock

from src.avails import (
    Wire,
    RemotePeer,
    SocketStore,
    connect,
    const,
    use,
    WireData,
)


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
        self.all_tasks = []
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
                task = asyncio.create_task(self.__accept_connection(initial_conn))
                self.all_tasks.append(task)

    async def start_socket(self):
        addr_info = await self.__loop.getaddrinfo(*self.address, family=const.IP_VERSION)
        sock_family, sock_type, _, _, address = addr_info[0]
        sock = const.PROTOCOL.create_async_server_sock(self.__loop, address, family=const.IP_VERSION, backlog=self.back_log)
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
            use.echo_print(f"Socket error: at {use.func_str(self.__accept_connection)} exp:{e}")
            initial_conn.close()

    async def verify(self, _conn):
        """
        :param _conn: connection from peer
        :returns peer_id: if verification is successful else None (implying socket to be removed)
        """
        hand_shake = await Wire.receive_async(_conn)
        if not hand_shake == const.CMD_VERIFY_HEADER:
            return None
        # hand_shake = SimplePeerBytes(_conn)
        # hand_shake = await hand_shake.receive(cmp_string=const.CMD_VERIFY_HEADER)
        # if not hand_shake:
        #     return None
        # peer_id = await SimplePeerBytes(_conn).receive()
        peer_id = await Wire.receive_async(_conn)
        peer_id = peer_id.decode(const.FORMAT)
        self.currently_in_connection[peer_id] += 1
        use.echo_print("verified peer", peer_id)  # debug
        return peer_id

    async def handle_peer(self, peer_id):
        sock = Dock.connected_peers.get_socket(peer_id)

        while self.currently_in_connection[peer_id]:
            try:
                raw_data = await asyncio.wait_for(Wire.receive_async(sock), self.max_timeout)
                data = WireData.load_from(raw_data)
                self.__process_data(data)
            except asyncio.TimeoutError:
                print("timedout", peer_id)
                continue
            except TypeError as tp:
                print("got type error possible data illformed", tp)

    def __process_data(self, _data):  # noqa # :todo: complete this
        if _data.header == const.CMD_TEXT:
            # page_handle.feed_user_data_to_page(_data.content, _data.id)
            ...
        elif _data.header == const.CMD_RECV_FILE:
            # self.start_thread(filemanager.file_receiver, _data)
            ...
        elif _data.header == const.CMD_RECV_FILE_AGAIN:
            # self.start_thread(filemanager.re_receive_file, _data)
            ...
        elif _data.header == const.CMD_RECV_DIR:
            # self.start_thread(directorymanager.directoryReceiver, _data)
            ...
        elif _data.header == const.CMD_CLOSING_HEADER:
            # self.disconnect_user(_conn, self._controller, peer_id)
            ...

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

    @classmethod
    async def connect_peer(cls, peer_obj: RemotePeer) -> connect.Socket:
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
        connection_socket = await connect.connect_to_peer(peer_obj, to_which=connect.BASIC_URI_CONNECT)
        Dock.connected_peers.add_peer_sock(peer_obj.id, connection_socket)
        return connection_socket

    @classmethod
    async def _verifier(cls, connection_socket):
        await Wire.send_async(connection_socket, const.CMD_VERIFY_HEADER)
        use.echo_print("sent header")  # debug
        await Wire.send_async(connection_socket, get_this_remote_peer().id)
        use.echo_print("Sent verification to ", connection_socket.getpeername())  # debug
        return True
