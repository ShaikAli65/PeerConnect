import asyncio
import itertools
import logging
from typing import Any

from src.avails.exceptions import FailedToSend

_logger = logging.getLogger(__name__)


class ReAddableOrderedQueue:
    def __init__(self, size):
        self.queue = asyncio.PriorityQueue(size)
        self._ordering = itertools.count()

    async def put(self, item: Any):
        return await self.queue.put((next(self._ordering), item))

    async def put_back(self, queue_item: Any, ordering):
        return await self.queue.put((ordering, queue_item))

    async def get(self):
        return await self.queue.get()

    def put_nowait(self, item: Any):
        return self.queue.put_nowait((next(self._ordering), item))

    def qsize(self):
        return self.queue.qsize()

    def empty(self):
        return self.queue.empty()

    def get_nowait(self):
        return self.queue.get_nowait()

    @property
    def maxsize(self):
        return self.queue.maxsize

    def task_done(self):
        return self.queue.task_done()

    async def join(self):
        return await self.queue.join()


class ReAddableQueue:
    def __init__(self, size):
        self.queue = asyncio.Queue(size)

    async def put_back(self, queue_item, ordering=None):
        return await self.queue.put(queue_item)

    async def put(self, item: Any):
        return await self.queue.put(item)

    async def get(self):
        return None, await self.queue.get()

    def get_nowait(self):
        return None, self.queue.get_nowait()

    def put_nowait(self, item: Any):
        return self.queue.put_nowait(item)

    def qsize(self):
        return self.queue.qsize()

    def empty(self):
        return self.queue.empty()

    @property
    def maxsize(self):
        return self.queue.maxsize

    def task_done(self):
        return self.queue.task_done()

    async def join(self):
        return await self.queue.join()


class MessageSocket:
    """
    Wrapping a Socket Transport with buffering if Socket fails, this will retry sending
    the failed messages to the Socket when it becomes available through the `update_transport` method.

    * Immediately sends messages using Socket if it is connected, otherwise buffers them

    Notes:
        * Does not own the socket transport, context manager enter and exit should be dealt with by the caller

    """

    def __init__(
          self,
          transport=None,
          buffer_size=None,
          should_prune_buffer_on_full=True,
          ordering=False,
          raise_on_send_failure=False,
          logger=None,
    ):
        self.stopping = False
        self.ping_sender = asyncio.Condition()
        self.max_buffer_size = buffer_size or 0
        self.ordering = ordering
        self.raise_on_send_failure = raise_on_send_failure
        self.buffer = ReAddableOrderedQueue(self.max_buffer_size) if ordering else ReAddableQueue(self.max_buffer_size)
        self._is_transport_connected = bool(transport)
        self.transport = transport
        self._finalized = False
        self._logger = logger or _logger
        self.should_prune_buffer_on_full = should_prune_buffer_on_full
        self._prev_connection_error = None

    async def update_transport(self, transport):
        self._is_transport_connected = True
        self.transport = transport
        async with self.ping_sender:
            self.ping_sender.notify_all()

    async def __call__(self, data):

        if not self._is_transport_connected:
            self._logger.debug(f"! transport not connected buffering data: {data=}")
            return await self._handle_failure(data)

        try:
            self._logger.debug(f"> sending data using connection: {data=!r}")
            await self.transport.send(data)
        except OSError as ce:
            self._is_transport_connected = False
            self._prev_connection_error = ce
            return await self._handle_failure(data)

    async def _handle_failure(self, data):
        future = asyncio.get_running_loop().create_future()
        await self._add_to_buffer(data, future)
        if self.raise_on_send_failure:
            ftos = FailedToSend(f"! transport failed, buffering data: {data=}")
            ftos.item = data
            ftos.future = future
            raise ftos from self._prev_connection_error
        else:
            return await future

    async def _send_buffer(self):
        while not self.stopping:
            async with self.ping_sender:
                await self.ping_sender.wait_for(
                    lambda: self.stopping or (
                        self._is_transport_connected
                        and not self.buffer.empty()
                    )
                )

            if self.stopping:
                break

            while not self.stopping and not self.buffer.empty():
                ordering, (msg, fut) = self.buffer.get_nowait()
                try:
                    if fut.done():
                        self._logger.debug(f"! dropping cancelled message: {msg=!r}, {fut=!r}")
                        continue
                    self._logger.debug(f"> sending data using connection: {msg=!r}")
                    fut.set_result(await self.transport.send(msg))
                except OSError:
                    self._is_transport_connected = False
                    await self._add_to_buffer(msg, fut, ordering)
                    break
                except AttributeError:
                    # transport is None, and we got \\"None does not have .send"\\ thing
                    self._is_transport_connected = False
                    await self._add_to_buffer(msg, fut, ordering)
                    break

    async def _add_to_buffer(self, item, fut, ordering=None):
        if self._is_buffer_full():
            if not self.should_prune_buffer_on_full:
                raise ValueError("failed buffer is full, cannot add new packet")
            self._prune_buffer()

        if ordering is None:
            await self.buffer.put((item, fut))
            return fut

        await self.buffer.put_back((item, fut), ordering)
        return fut

    def _is_buffer_full(self):
        return 0 < self.max_buffer_size <= self.buffer.qsize()

    def _prune_buffer(self):
        """Logs a warning and removes the oldest queued message."""
        try:
            _ordering, (msg, fut) = self.buffer.get_nowait()
        except asyncio.QueueEmpty:
            return None

        if not fut.done():
            ftos = FailedToSend("failed buffer is full, discarding oldest packet")
            ftos.item = msg
            fut.set_exception(ftos)
        self._logger.warning(
            f"discarding socket message {msg}, buffer full",
            exc_info=True,
        )
        return msg

    def _may_be_prune_buffer(self):
        """Logs a warning and removes top element from queue"""
        if self._is_buffer_full():
            return self._prune_buffer()
        return None

    def _fail_pending_buffer(self):
        while not self.buffer.empty():
            _ordering, (msg, fut) = self.buffer.get_nowait()
            if fut.done():
                continue
            ftos = FailedToSend("message socket closed before buffered packet was sent")
            ftos.item = msg
            fut.set_exception(ftos)

    async def __aenter__(self):
        self._buffer_sender_task = asyncio.create_task(self._send_buffer(),
                                                       name="msg-socket-buffer-sender")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._finalized:
            return

        if not self.buffer.empty():
            self._logger.warning(f"failure buffer not empty len={self.buffer.qsize()}")
            self._fail_pending_buffer()

        self.stopping = True
        async with self.ping_sender:
            self.ping_sender.notify_all()

        await self._buffer_sender_task
        self._logger.debug("closed front end websocket")
        self._finalized = True
