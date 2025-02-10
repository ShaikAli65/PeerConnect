import asyncio as _asyncio
import socket as _socket
from abc import ABC, abstractmethod
from typing import Optional

from src.avails._asocket import Socket


class NetworkProtocol(ABC):
    __slots__ = ()

    @staticmethod
    @abstractmethod
    def create_async_sock(
            loop: _asyncio.AbstractEventLoop,
            family: _socket.AddressFamily,
            fileno: int = None,
    ):
        """Create an asynchronous socket."""
        return NotImplemented

    @staticmethod
    @abstractmethod
    def create_sync_sock(
            family: _socket.AddressFamily = _socket.AF_INET, fileno: int = None
    ):
        """Create a synchronous socket."""
        return NotImplemented

    @staticmethod
    @abstractmethod
    def create_async_server_sock(
            loop: _asyncio.AbstractEventLoop,
            bind_address,
            *,
            family: _socket.AddressFamily = _socket.AF_INET,
            backlog: int | None = None,
            fileno: int = None,
    ):
        """Create an asynchronous server socket."""
        return NotImplemented

    @staticmethod
    @abstractmethod
    def create_sync_server_sock(
            bind_address,
            *,
            family: _socket.AddressFamily = _socket.AF_INET,
            backlog: int | None = None,
            fileno: int = None,
    ):
        """Create a synchronous server socket."""
        return NotImplemented

    @staticmethod
    @abstractmethod
    async def create_connection_async(loop, address, timeout=None) -> Socket:
        return NotImplemented

    def __format__(self, format_spec):
        return self.__repr__().__format__(format_spec)


class TCPProtocol(NetworkProtocol):
    __slots__ = ()

    @staticmethod
    def create_async_sock(
            loop: _asyncio.AbstractEventLoop,
            family: _socket.AddressFamily = _socket.AF_INET,
            fileno: Optional[int] = None,
    ) -> Socket:
        sock = Socket(family, _socket.SOCK_STREAM, -1, fileno)
        sock.setblocking(False)
        sock.set_loop(loop)
        return sock

    @staticmethod
    def create_sync_sock(
            family: _socket.AddressFamily = _socket.AF_INET, fileno: Optional[int] = None
    ):
        return Socket(family, _socket.SOCK_STREAM, -1, fileno)

    @staticmethod
    def create_async_server_sock(
            loop: _asyncio.AbstractEventLoop,
            bind_address,
            *,
            family: _socket.AddressFamily = _socket.AF_INET,
            backlog: int | None = None,
            fileno: Optional[int] = None,
    ):
        server_sock = Socket(family, _socket.SOCK_STREAM, -1, fileno)
        server_sock.bind(bind_address)
        server_sock.setblocking(False)
        server_sock.set_loop(loop)
        server_sock.listen(backlog)
        return server_sock

    @staticmethod
    def create_sync_server_sock(
            bind_address,
            *,
            family: _socket.AddressFamily = _socket.AF_INET,
            backlog: int | None = None,
            fileno: Optional[int] = None,
    ):
        server_sock = Socket(family, _socket.SOCK_STREAM, -1, fileno)
        server_sock.bind(bind_address)
        server_sock.listen(backlog)
        return server_sock

    @classmethod
    async def create_connection_async(
            cls, loop: _asyncio.AbstractEventLoop, address, timeout=None
    ) -> Socket:
        addr_info = await loop.getaddrinfo(*address[:2], type=_socket.SOCK_STREAM)
        addr_family, sock_type, _, _, resolved_address = addr_info[0]

        if addr_family == _socket.AF_INET6:
            resolved_address = *resolved_address[:3], address[3]
            # persist scope_id from address, in linux getaddrinfo
            # betrays by sending 0 as the scope id after resolving
            # which simply does not work, cause linux needs exact scope_id to make connection from

        sock = cls.create_async_sock(loop, addr_family)
        await (
            _asyncio.wait_for(sock.aconnect(resolved_address), timeout)
            if timeout
            else sock.aconnect(resolved_address)
        )
        return sock

    def __repr__(self):
        return "<connect.TCPProtocol>"

    def __format__(self, format_spec):
        return self.__repr__().__format__(format_spec)


class UDPProtocol(NetworkProtocol):
    __slots__ = ()

    @staticmethod
    def create_async_sock(
            loop: _asyncio.AbstractEventLoop,
            family: _socket.AddressFamily = _socket.AF_INET,
            fileno: Optional[int] = None,
    ):
        sock = Socket(family, _socket.SOCK_DGRAM, _socket.IPPROTO_UDP, fileno)
        sock.setblocking(False)
        sock.set_loop(loop)
        return sock

    @staticmethod
    def create_sync_sock(
            family: _socket.AddressFamily = _socket.AF_INET, fileno: Optional[int] = None
    ):
        return Socket(family, _socket.SOCK_DGRAM, -1, fileno)

    @staticmethod
    def create_async_server_sock(
            loop: _asyncio.AbstractEventLoop,
            bind_address,
            *,
            family: _socket.AddressFamily = _socket.AF_INET,
            backlog: int | None = None,
            fileno: Optional[int] = None,
    ):
        server_sock = Socket(family, _socket.SOCK_DGRAM, -1, fileno)
        server_sock.setblocking(False)
        server_sock.set_loop(loop)
        server_sock.bind(bind_address)
        # server_sock.listen(backlog)
        return server_sock

    @staticmethod
    def create_sync_server_sock(
            bind_address,
            *,
            family: _socket.AddressFamily = _socket.AF_INET,
            backlog: int | None = None,
            fileno: Optional[int] = None,
    ):
        server_sock = Socket(family, _socket.SOCK_DGRAM, -1, fileno)
        server_sock.bind(bind_address)
        server_sock.listen(backlog)
        return server_sock

    @classmethod
    async def create_connection_async(
            cls, loop: _asyncio.AbstractEventLoop, address, timeout=None
    ) -> Socket:
        addr_info = await loop.getaddrinfo(*address, type=_socket.SOCK_DGRAM)
        addr_family, sock_type, _, _, address = addr_info[0]

        sock = cls.create_async_sock(loop, addr_family)
        sock.connect(address)
        return sock

    def __repr__(self):
        return "<connect.UDProtocol>"
