from collections import defaultdict

from src.avails.connect import Connection, Socket, is_socket_connected
from src.avails.mixins import AExitStackMixIn, singleton_mixin
from src.core import Dock


async def start_watcher():
    await Dock.exit_stack.enter_async_context(Watcher())


@singleton_mixin
class Watcher(AExitStackMixIn):
    def __init__(self):
        super().__init__()
        self.sockets = defaultdict(list)

    def add_new_socket(self, socket: Socket, connection: Connection):
        self.sockets[connection.peer].append((socket, connection))
        self._exit_stack.enter_context(socket)

    async def refresh(self, connection: Connection):
        for sock, conn in self.sockets[connection.peer].copy():
            if conn is connection:
                if is_socket_connected(sock):
                    return True
                else:
                    self.sockets[connection.peer].remove((sock, connection))
                    sock.close()  # RIP

        return False
