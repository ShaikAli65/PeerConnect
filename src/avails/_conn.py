import time
from typing import Any, NamedTuple, TYPE_CHECKING

from src.avails._asocket import Socket
from src.avails import const
import asyncio as _asyncio


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


class Connection(NamedTuple):
    """
    To represent A p2p connection

    Note:
        does not own the resource (socket), just a handy wrapper to pass between functions

    Attributes:
        socket: underlying socket (for introspection)
        send: sender API, async callable that returns when data passed is sent successfully
        recv: receiver API, async callable that returns bytes with requested length
        peer: peer object of other end
    """
    socket: Socket
    send: Sender
    recv: Receiver
    if TYPE_CHECKING:
        from src.avails import RemotePeer
        peer: RemotePeer
    else:
        peer: Any

    @staticmethod
    def create_from(socket, peer):
        return Connection(socket, Sender(socket), Receiver(socket), peer)

    def __enter__(self):
        return self.socket

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.socket.__exit__(exc_type, exc_val, exc_tb)
