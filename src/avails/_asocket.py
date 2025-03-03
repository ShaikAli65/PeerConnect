import socket as _socket
from typing import Optional, Self, IO

import asyncio as _asyncio


class Socket(_socket.socket):
    """
    The Socket class is a custom subclass of Python's built-in _socket.socket class,
    designed to integrate with asyncio for asynchronous I/O operations.
    It provides both synchronous and asynchronous methods for common socket operations.

    Attributes:
        __loop (asyncio.AbstractEventLoop): The event loop used for asynchronous operations.
         This must be set using the set_loop method before any asynchronous methods are called.
    """

    __loop: Optional[_asyncio.AbstractEventLoop] = None

    # def __init__(self, family: _socket.AddressFamily | int = -1, _type: _socket.SocketKind | int = -1, proto: int = -1, fileno: int | None = None) -> None:
    #     super().__init__(family, _type, proto, fileno)

    def set_loop(self, loop: _asyncio.AbstractEventLoop):
        """
        Sets the event loop to be used for asynchronous operations.

        Parameters:
            loop (asyncio.AbstractEventLoop): The event loop instance.
        """
        self.__loop = loop

    def remove_loop(self):
        self.__loop = None

    def accept(self) -> tuple[Self, tuple[str, int]]:
        """
        Accepts a connection, returning a new custom Socket instance and the address of the client.
        Returns:
            custom_socket (Socket): A new Socket instance.
            addr (Tuple[str, int]): The address of the client.
        """
        fd, addr = self._accept()  # noqa
        # Cast the socket to the custom Socket class

        custom_socket = self.__class__(self.family, self.type, self.proto, fileno=fd)
        if _socket.getdefaulttimeout() is None and self.gettimeout():
            custom_socket.setblocking(True)
        if self.__loop:
            custom_socket.set_loop(self.__loop)
        return custom_socket, addr

    async def aaccept(self):
        return await self.__loop.sock_accept(self)

    def arecv(self, bufsize):
        return self.__loop.sock_recv(self, bufsize)

    async def aconnect(self, __address):
        return await self.__loop.sock_connect(self, __address)

    async def asendall(self, data):
        return await self.__loop.sock_sendall(self, data)

    async def asendfile(
            self,
            file: IO[bytes],
            offset: int = 0,
            count: int | None = None,
            *,
            fallback: bool | None = None,
    ):
        return await self.__loop.sock_sendfile(
            self, file, offset, count, fallback=fallback
        )

    async def asendto(self, data, address):
        return await self.__loop.sock_sendto(self, data, address)

    async def arecv_into(self, buffer):
        return await self.__loop.sock_recv_into(self, buffer)

    async def arecvfrom_into(self, buffsize):
        return await self.__loop.sock_recvfrom(self, buffsize)

    async def arecvfrom(self, buffsize):
        return await self.__loop.sock_recvfrom(self, buffsize)
