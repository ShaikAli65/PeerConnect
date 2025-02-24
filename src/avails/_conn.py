import asyncio as _asyncio
import struct
import time
from asyncio.trsock import TransportSocket
from typing import Any, NamedTuple, TYPE_CHECKING

# import src.avails.wire as wire
from src.avails import const, wire
from src.avails._asocket import Socket


class _PauseMixIn:
    __slots__ = ()

    def pause(self):
        self._limiter.clear()  # noqa


class _ResumeMixIn:
    __slots__ = ()

    def resume(self):
        self._limiter.set()  # noqa


class ThroughputMixin:
    """
    Mixin to provide common asynchronous I/O and throughput measurement.
    """

    BYTES_PER_KB = const.BYTES_PER_KB
    RATE_WINDOW = const.RATE_WINDOW

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bytes_total = 0
        self._window_start = time.perf_counter()
        self.rate = 0.0

    def _update_throughput(self, nbytes, current_time):
        """
        Update the throughput counters.

        :param nbytes: number of bytes transferred during the operation.
        :param current_time: the current time (using time.perf_counter()).
        """
        self._bytes_total += nbytes
        dt = current_time - self._window_start
        if dt >= self.RATE_WINDOW:
            self.rate = self._bytes_total / self.BYTES_PER_KB / dt
            self._bytes_total = 0
            self._window_start = current_time

    @property
    def last_updated_time(self):
        return self._window_start


class Sender(_PauseMixIn, _ResumeMixIn, ThroughputMixin):
    __slots__ = ('sock', 'send_func', '_limiter',
                 '_bytes_total', '_window_start', 'rate')

    def __init__(self, sock, *args, **kwargs):
        self.sock = sock
        loop = _asyncio.get_event_loop()
        self.send_func = loop.sock_sendall
        self._limiter = _asyncio.Event()
        self._limiter.set()
        super().__init__(*args, **kwargs)

    async def __call__(self, buf: bytes):
        await self._limiter.wait()
        await self.send_func(self.sock, buf)
        return self._update_throughput(len(buf), time.perf_counter())

    def __repr__(self):
        return f"<connect.{type(self)}(>{self.sock.getpeername()}, rate={self.rate}, slow={not self._limiter.is_set()})>"


class Receiver(_PauseMixIn, _ResumeMixIn, ThroughputMixin):
    __slots__ = ('sock', 'recv_func', '_limiter',
                 '_bytes_total', '_window_start', 'rate')

    def __init__(self, sock, *args, **kwargs):
        self.sock = sock
        loop = _asyncio.get_event_loop()
        self.recv_func = loop.sock_recv
        self._limiter = _asyncio.Event()
        self._limiter.set()
        super().__init__(*args, **kwargs)

    async def __call__(self, nbytes: int):
        await self._limiter.wait()
        data = await self.recv_func(self.sock, nbytes)
        self._update_throughput(nbytes, time.perf_counter())
        return data

    def __repr__(self):
        return f"<connect.{type(self)}(>{self.sock.getpeername()}, rate={self.rate}, slow={not self._limiter.is_set()})>"


class Connection(NamedTuple):
    """
    To represent A p2p connection

    Recommended to use async with which acquires the underlying lock,
    this makes sure that resource is kept within

    Note:
        does not own the resource (socket), just a handy wrapper to pass between functions


    Attributes:
        socket: underlying socket (for introspection)
        send: sender API, async callable that returns when data passed is sent successfully
        recv: receiver API, async callable that returns bytes with requested length
        peer: peer object of other end
    """
    socket: TransportSocket
    send: Sender
    recv: Receiver

    if TYPE_CHECKING:
        from src.avails import RemotePeer
        peer: RemotePeer
    else:
        peer: Any

    lock: _asyncio.Lock

    @staticmethod
    def create_from(socket: Socket, peer):
        return Connection(TransportSocket(socket), Sender(socket), Receiver(socket), peer, _asyncio.Lock())

    async def __aenter__(self):
        await self.lock.acquire()
        return self

    async def __aexit__(self, *exp_details):
        self.lock.release()


class MsgConnection:
    """Send or Receive WireData object from connection"""
    __slots__ = '_connection',  # 'recv', 'send'
    _connection: Connection

    def __init__(self, connection):
        self._connection = connection

    async def send(self, data):
        byted_data = bytes(data)  # marshall
        data_size = struct.pack("!I", len(byted_data))
        return await self._connection.send(data_size + byted_data)

    if TYPE_CHECKING:
        async def send(self, data: wire.WireData): ...

    async def recv(self):
        data_size = struct.unpack("!I", await self._connection.recv(4))[0]
        raw_data = await self._connection.recv(data_size)
        return wire.WireData.load_from(raw_data)

    @property
    def socket(self):
        return self._connection.socket

    @property
    def peer(self):
        return self._connection.peer


class MsgConnectionNoRecv(MsgConnection):
    __slots__ = ()

    async def recv(self, *args):
        raise NotImplementedError("not allowed")
