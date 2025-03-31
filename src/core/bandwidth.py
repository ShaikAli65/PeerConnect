import asyncio
from collections import defaultdict

from src.avails import RemotePeer, const, use
from src.avails.connect import Connection, Socket, is_socket_connected
from src.avails.mixins import AExitStackMixIn, singleton_mixin


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
        ] = defaultdict(
            dict)  # connection related to remotepeer keyed and valued with connection tuple and raw socket respectively
        self._total_socks = 0
        self._maintenance_task = asyncio.Task(self._maintenance())

    def watch(self, socket: Socket, connection: Connection):
        self.sockets[connection.peer][connection] = socket
        self._exit_stack.enter_context(socket)
        self._total_socks += 1

    async def refresh(self, peer, *connections: Connection):
        connections = set(connections)
        active = set()
        not_active = set()

        for conn, sock in self.sockets[peer].items():
            if conn not in connections:
                continue
            if is_socket_connected(sock):
                active.add(conn)
            else:
                sock.close()  # RIP
                not_active.add(conn)

        for conn in not_active:
            self.sockets[peer].pop(conn)
            self._total_socks -= 1

        return active, not_active

    async def refresh_all(self, peer):
        """Checks all the connections related to peer

        Args:
            peer(RemotePeer): to check

        """
        await self.refresh(peer, *self.sockets[peer].keys())

    async def _maintenance(self):
        while True:
            await asyncio.sleep(1)
            if self.total_connections < const.MAX_TOTAL_CONNECTIONS:
                continue

            to_be_removed = []

            for peer, conns in self.sockets.items():
                for conn, sock in conns.items():
                    last_accessed = max(conn.send.last_updated_time, conn.recv.last_updated_time)
                    if last_accessed >= const.MAX_IDLE_TIME_FOR_CONN:
                        sock.close()
                        to_be_removed.append((peer, conn))

            for peer, conn in to_be_removed:
                self.sockets[peer].pop(conn)

    async def close_if_not_active(self, peer, conn):
        """
        Args:
              peer(RemotePeer): related peer object
              conn(Connection): connection to check
        Returns:
            bool: True if connection is inactive, False is connection is active and not getting closed
        """
        active, closed = await self.refresh(peer, conn)
        if conn in closed or conn not in active:
            await self.request_closing(conn)
            return True
        return False

    async def request_closing(self, conn: Connection):
        if conn in self.sockets.get(conn.peer, {}):
            self.sockets[conn.peer][conn].close()

    @property
    def total_connections(self):
        return self._total_socks

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await use.safe_cancel_task(self._maintenance_task)
