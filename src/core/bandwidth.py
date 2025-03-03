from collections import defaultdict

from src.avails import RemotePeer
from src.avails.connect import Connection, Socket, is_socket_connected
from src.avails.mixins import AExitStackMixIn, singleton_mixin
from src.core import public


async def start_watcher():
    await public.Dock.exit_stack.enter_async_context(Watcher())


@singleton_mixin
class Watcher(AExitStackMixIn):
    def __init__(self):
        super().__init__()
        self.sockets: dict[
            RemotePeer,
            dict[
                Connection,
                Socket,
            ],
        ] = defaultdict(dict)  # connection related to remotepeer keyed with connection tuple and valued with raw socket

    def watch(self, socket: Socket, connection: Connection):
        self.sockets[connection.peer][connection] = socket
        self._exit_stack.enter_context(socket)

    async def refresh(self, peer, *connections: Connection):
        active = set()
        not_active = set()
        for conn, sock in tuple(self.sockets[peer].items()):
            if conn not in connections:
                continue
            if is_socket_connected(sock):
                active.add(conn)
            else:
                self.sockets[peer].pop(conn)
                sock.close()  # RIP
                not_active.add(conn)

        return active, not_active

    async def refresh_all(self, peer):
        """Checks all the connections related to peer

        Args:
            peer(RemotePeer): to check

        """
        await self.refresh(peer, *self.sockets[peer].keys())
