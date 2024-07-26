import asyncio
import asyncio as _asyncio
import random
import socket as _socket
from typing import IO, Self, Optional
from . import const


class Socket(_socket.socket):
    """
    The Socket class is a custom subclass of Python's built-in _socket.socket class,
    designed to integrate with asyncio for asynchronous I/O operations.
    It provides both synchronous and asynchronous methods for common socket operations.

    Attributes
        __loop (asyncio.AbstractEventLoop): The event loop used for asynchronous operations.
         This must be set using the set_loop method before any asynchronous methods are called.
    """

    __loop: _asyncio.AbstractEventLoop = None

    # def __init__(self, family: _socket.AddressFamily | int = -1, _type: _socket.SocketKind | int = -1, proto: int = -1, fileno: int | None = None) -> None:
    #     super().__init__(family, _type, proto, fileno)

    def set_loop(self, loop: _asyncio.AbstractEventLoop):
        """
        Sets the event loop to be used for asynchronous operations.

        Parameters:
            loop (asyncio.AbstractEventLoop): The event loop instance.
        """
        self.__loop = loop

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
        return custom_socket, addr

    async def aaccept(self):
        return await self.__loop.sock_accept(self)

    async def arecv(self, bufsize):
        return await self.__loop.sock_recv(self, bufsize)

    async def aconnect(self, __address) -> Self:
        return await self.__loop.sock_connect(self, __address)

    async def asendall(self, data):
        return await self.__loop.sock_sendall(self, data)

    async def asendfile(self, file: IO[bytes],
                        offset: int = 0,
                        count: int | None = None,
                        *,
                        fallback: bool | None = None):
        return await self.__loop.sock_sendfile(self, file, offset, count, fallback=fallback)

    async def arecv_into(self, buffer):
        return await self.__loop.sock_recv_into(self, buffer)

    async def arecvfrom_into(self, buffsize):
        return await self.__loop.sock_recvfrom(self, buffsize)

    async def arecvfrom(self, buffsize):
        return await self.__loop.sock_recvfrom(self, buffsize)


def create_sock(family: _socket.AddressFamily | int = -1, _type: _socket.SocketKind | int = -1,proto: int = -1, fileno: int | None = None):
    if not family:
        family = const.IP_VERSION

    sock = Socket(family, _type, proto, fileno)
    sock.setblocking(False)
    sock.set_loop(_asyncio.get_running_loop())
    return sock


async def create_connection(address, *, sock_family=None, sock_type=None, timeout=None) -> Socket:
    if sock_family is None:
        sock_family = const.IP_VERSION
    if sock_type is None:
        sock_type = const.PROTOCOL

    loop = asyncio.get_running_loop()
    addr_info = await loop.getaddrinfo(*address, family=sock_family, type=sock_type)

    sock_family, sock_type, _, _, address = addr_info[0]

    sock = Socket(sock_family, sock_type)
    sock.setblocking(False)
    sock.set_loop(_asyncio.get_event_loop())

    try:
        if timeout:
            return await _asyncio.wait_for(sock.aconnect(address), timeout)
    except _asyncio.TimeoutError:
        raise

    return await sock.aconnect(address)


BASIC_URI_CONNECT = 13
REQ_URI = 12


async def connect_to_peer(_peer_obj=None, to_which: int = BASIC_URI_CONNECT, timeout=None) -> Optional[Socket]:
    """
    Creates a basic socket connection to the peer_obj passed in.
    The another argument :param to_which: specifies to what uri should the connection made,
    pass `const.REQ_URI_CONNECT` to connect to req_uri of peer
    *args will be passed into socket.setsockoption
    :param timeout:
    :param _peer_obj: RemotePeer object
    :param to_which:
    :return:
    """
    if not _peer_obj:
        raise ValueError("_peer_obj cannot be None")

    addr = _peer_obj.req_uri if to_which == REQ_URI else _peer_obj.uri
    address_info = _socket.getaddrinfo(addr[0], addr[1], type=_socket.SOCK_STREAM)[0]
    address = address_info[4]  # [:2]
    sock_family = address_info[0]
    sock_type = address_info[1]

    try:
        return await create_connection(address, sock_family=sock_family, sock_type=sock_type, timeout=timeout)
    except _asyncio.TimeoutError:
        return None
    except Exception as e:
        print(f"Error connecting to peer: {e}")
        return None


def is_socket_connected(sock: Socket):
    blocking = sock.getblocking()
    sock.setblocking(False)
    try:
        sock.getpeername()
        data = sock.recv(1, _socket.MSG_PEEK)
        return data != b''
    except BlockingIOError:
        return True
    except (OSError, _socket.error):
        return False
    finally:
        try:
            sock.setblocking(blocking)
        except OSError:
            return False


def get_free_port() -> int:
    """Gets a free port from the system."""
    random_port = random.randint(10000, 65535)
    while not is_port_empty(random_port):
        random_port = random.randint(10000, 65535)
    return random_port


def is_port_empty(port):
    try:
        with _socket.socket(const.IP_VERSION, _socket.SOCK_STREAM) as s:
            s.bind((const.THIS_IP, port))
            return True
    except (OSError, _socket.error, _socket.gaierror):
        return False
