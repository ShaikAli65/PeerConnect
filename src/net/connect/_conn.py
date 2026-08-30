from asyncio import Event, get_running_loop, sleep
from asyncio.trsock import TransportSocket
from enum import Enum
from time import perf_counter
from typing import Annotated, Awaitable, Callable, TypeVar

from src.avails import RemotePeer, const, use
from src.avails.exceptions import FailedToReceive
from ._asocket import Socket

__all__ = (
    "ThroughputMixin",
    "Sender",
    "Receiver",
    "Connection",
    "ChunkedReceiver",
    "ConnectionType",
)


class _PauseMixIn:
    __slots__ = ()

    def pause(self):
        getattr(self, '_limiter').clear()


class _ResumeMixIn:
    __slots__ = ()

    def resume(self):
        getattr(self, '_limiter').set()


class ThroughputMixin:
    """
    Mixin to provide common asynchronous I/O and throughput measurement.

    You can set `max_rate_limit` to a valid rate, that limits transfer rate (in KB/s)
    set it back to None to default
    """

    BYTES_PER_KB = const.BYTES_PER_KB
    RATE_WINDOW = const.RATE_CALC_WINDOW
    CALIBRATION_FACTOR = 1.06  # Compensate for overhead

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bytes_total = 0
        self._window_start = perf_counter()
        self.rate = 0.0
        self.max_rate_limit = None
        self._tokens = 0.0  # In bytes
        self._last_token_update = perf_counter()

    async def _throttle(self, nbytes):
        if self.max_rate_limit is None:
            return

        current_time = perf_counter()
        elapsed = current_time - self._last_token_update
        self._last_token_update = current_time
        rate_limit = self.effective_rate_limit

        # Add new tokens
        new_tokens = rate_limit * self.BYTES_PER_KB * elapsed
        self._tokens = min(self._tokens + new_tokens, rate_limit * self.BYTES_PER_KB * 1)  # Max 1s burst

        # Check if we have enough tokens
        while self._tokens < nbytes:
            deficit = nbytes - self._tokens
            wait_time = deficit / (rate_limit * self.BYTES_PER_KB)
            await sleep(wait_time)

            # Update tokens after waiting
            current_time = perf_counter()
            elapsed = current_time - self._last_token_update
            self._last_token_update = current_time
            self._tokens += rate_limit * self.BYTES_PER_KB * elapsed

        self._tokens -= nbytes

    @property
    def effective_rate_limit(self):
        if self.max_rate_limit is None:
            return float('inf')
        return self.max_rate_limit * self.CALIBRATION_FACTOR

    def _update_throughput(self, nbytes):
        """
        Update the throughput counters.
        :param nbytes: number of bytes transferred during the operation.
        """

        current_time = perf_counter()
        self._bytes_total += nbytes
        dt = current_time - self._window_start
        if dt >= self.RATE_WINDOW:
            self.rate = self._bytes_total / self.BYTES_PER_KB / dt
            self._bytes_total = 0
            self._window_start = current_time

        return nbytes

    @staticmethod
    def _format_rate(rate_kbps):
        """Convert KB/s to human-readable format with appropriate units"""
        if rate_kbps < 1:
            return f"{rate_kbps * 1024:.1f} B/s"
        elif rate_kbps < 1024:
            return f"{rate_kbps:.1f} KB/s"
        else:
            return f"{rate_kbps / 1024:.1f} MB/s"

    @property
    def readable_rate(self):
        return self._format_rate(self.rate)

    @property
    def readable_mx_rate(self):
        return self._format_rate(self.max_rate_limit) if self.max_rate_limit else "inf"

    @property
    def last_updated_time(self):
        return self._window_start


class _ReprMixin:
    __slots__ = ()

    def __repr__(self):
        return f"<{__package__}.{type(self).__name__}(" \
               f">{getattr(self, '_peer_name')}, " \
               f"rx={getattr(self, 'readable_rate')}, " \
               f"paused={not getattr(self, '_limiter').is_set()}, " \
               f"mxr={getattr(self, 'readable_mx_rate')}" \
               ")>"


class Sender(
    ThroughputMixin,
    _PauseMixIn,
    _ResumeMixIn,
    _ReprMixin,
):
    __slots__ = "sock", "_send_func", "_limiter", "_peer_name", "max_rate_limit"
    MAX_CHUNK_RATIO = 0.1  # Max 10% of bucket size

    def __init__(self, sock, *args, **kwargs):
        self.sock = sock
        self._peer_name = sock.getpeername()
        self._send_func = get_running_loop().sock_sendall
        self._limiter = Event()
        self._limiter.set()
        super().__init__(*args, **kwargs)

    async def _process_chunk(self, chunk):
        await self._limiter.wait()
        nbytes = len(chunk)
        await self._throttle(nbytes)
        await self._send_func(self.sock, chunk)
        return self._update_throughput(nbytes)

    async def __call__(self, buf: bytes | memoryview) -> Annotated[int, "bytes sent"]:
        total_sent = 0
        length = len(buf)

        with memoryview(buf) as mv:  # <-- wrap the original bytes in a memoryview
            # TODO: try to align the chunk size to the socket buffer size and actual packet size on the wire
            while total_sent < length:
                # Dynamic chunk sizing
                if self.max_rate_limit:
                    chunk_size = min(
                        length - total_sent,
                        int(self.max_rate_limit * self.BYTES_PER_KB * self.MAX_CHUNK_RATIO)
                    )
                else:
                    chunk_size = length - total_sent

                chunk = mv[total_sent: total_sent + chunk_size]
                await self._process_chunk(chunk)
                total_sent += chunk_size

        return total_sent


class Receiver(
    ThroughputMixin,
    _PauseMixIn,
    _ResumeMixIn,
    _ReprMixin,
):
    __slots__ = "sock", "_recv_func", "_limiter", "_peer_name", "max_rate_limit"

    def __init__(self, sock, *args, **kwargs):
        self.sock = sock
        self._peer_name = sock.getpeername()

        self._recv_func = get_running_loop().sock_recv
        self._limiter = Event()
        self._limiter.set()
        super().__init__(*args, **kwargs)

    async def __call__(self, nbytes: int):
        await self._limiter.wait()
        received_data = bytearray()

        while len(received_data) < nbytes:
            chunk = await self._recv_func(self.sock, nbytes - len(received_data))
            if chunk == b"":  # Handle premature disconnection
                ce = ConnectionError("Connection closed during data reception")
                setattr(ce, 'received_data', bytes(received_data))
                raise ce

            received_data += chunk

            received_bytes = len(chunk)
            await self._throttle(received_bytes)
            self._update_throughput(received_bytes)

        return bytes(received_data)


ReceiverType = TypeVar("ReceiverType", Receiver, Callable[[int], Awaitable[bytes]])


async def ChunkedReceiver(receiver: ReceiverType, size: int, chunk_size: int):
    """
    Asynchronously receives data in chunks from a Receiver or compatible callable.

    This function is a generator that yields chunks of received data until the
    specified total `size` is received. It repeatedly calls the `receiver` with
    chunk sizes, adjusted dynamically to avoid over-reading near the end.

    Useful when live control is needed upon receiving data

    Args:
        receiver (ReceiverType): Either an instance of `Receiver` or an async callable
                                 accepting a byte count and returning `bytes`.
        size (int): Total number of bytes expected to be received.
        chunk_size (int): Maximum size of each chunk to be received.

    Yields:
        bytes: A chunk of received data (never larger than `chunk_size`).

    Raises:
        FailedToReceive: If the connection is interrupted and total expected data
                         could not be received.
                        (`FailedToReceive.received` field can be used to check for
                         how much data is received successfully).

    """

    remaining_bytes = size
    while remaining_bytes > 0:
        data = await receiver(min(chunk_size, remaining_bytes))
        if not data:
            raise FailedToReceive(size - remaining_bytes)
        remaining_bytes -= len(data)
        yield data


class ConnectionType(Enum):
    MESSAGE = 0
    TRANSFERS = 1
    TBD = 2  # to be defined


@use.provide__init__(slots=True)
class Connection:
    """
    To represent A p2p connection

    Recommended to use ``async with`` which acquires the underlying lock,
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
    peer: RemotePeer
    lock: use.Lock
    type: ConnectionType

    @classmethod
    def create_from(cls, socket: Socket, peer):
        return cls(
            TransportSocket(socket), Sender(socket), Receiver(socket), peer, use.Lock(), ConnectionType.TBD  # noqa
        )

    def __enter__(self):
        raise RuntimeWarning("use async with!")

    async def __aenter__(self):
        await self.lock.acquire()
        return self

    async def __aexit__(self, *exp_details):
        self.lock.release()

    @property
    def busy(self):
        return self.lock.locked()
