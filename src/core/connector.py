"""
Closely coupled with core.acceptor
Works with connecting to other peer
"""
import logging
import textwrap

from src.avails import RemotePeer, SocketCache, Wire, WireData, connect, const, use
from src.avails.mixins import singleton_mixin
from src.core import Dock, get_this_remote_peer
from src.transfers import HEADERS

_logger = logging.getLogger(__name__)


class Connector:
    _current_connected: connect.Socket
    connections = SocketCache()

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
            header=HEADERS.CMD_BASIC_CONN,
            msg_id=get_this_remote_peer().peer_id,
        )
        await Wire.send_async(connection_socket, bytes(verification_data))
        _logger.info(f"Sent verification to {connection_socket.getpeername()}")  # debug
        return True


@singleton_mixin
class Connector1:
    __slots__ = ()

    msg_connections = {}
    transfer_connections = {}

    _conn_count = 0

    async def get_msg_conn(self, peer: RemotePeer):
        ...

    async def get_file_conn(self, peer: RemotePeer):
        ...

    async def max_connections_that_can_be_made(self, peer: RemotePeer):
        return const.MAX_CONNECTIONS_BETWEEN_PEERS - self.active_connections_count(peer)

    def active_connections_count(self, peer: RemotePeer):
        c = 0
        if i := self.msg_connections.get(peer, None):
            c += len(i)
        if i := self.transfer_connections.get(peer, None):
            c += len(i)
        return c

    @property
    def conn_count(self):
        return self._conn_count
