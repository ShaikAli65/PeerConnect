import asyncio
import itertools
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from avails.exceptions import InvalidStateError
from src.avails.exceptions import FailedToSend

_logger = logging.getLogger(__name__)

__all__ = ("MessageSocket", "BufferedSend")


@dataclass(order=True, slots=True)
class BufferedSend:
    ordering: int
    data: Any = field(compare=False)
    future: asyncio.Future = field(compare=False)


class MessageSocket:
    """
    MessageSocket facilitates the management of message sending over a transport
    connection with optional buffering, ordering, and error handling.

    This class provides functionality to send messages over a transport, handle
    disconnections and connection errors gracefully, buffer messages when the
    transport is unavailable, and ensure ordered delivery if specified. It is
    suitable for use in scenarios where reliable message delivery and queuing
    during temporary transport unavailability are desired.
    """

    def __init__(
          self,
          transport=None,
          use_buffering=True,
          buffer_size=None,
          should_prune_buffer_on_full=True,
          ordering=False,
          raise_on_send_failure=False,
          logger=None,
    ):
        """
        Args:
            ordering (bool):
                Specifies whether messages should be sent in the same order as they are provided
                when they are failed to send.

            raise_on_send_failure (bool): Determines whether to raise an exception or
                                          buffer messages upon send failure.

            transport: The transport object used for sending messages.

            use_buffering (bool): Indicates whether buffering should be enabled for
                                  failed message sends, if False, exceptions will be raised immediately.

            should_prune_buffer_on_full (bool): Specifies whether to prune the buffer
                                                when it becomes full.
        """

        self.connection_restablished = asyncio.Condition()
        self.ordering = ordering
        self.raise_on_send_failure = raise_on_send_failure
        self.buffer = asyncio.PriorityQueue[BufferedSend](buffer_size)
        self.transport = transport
        self.use_buffering = use_buffering
        self.should_prune_buffer_on_full = should_prune_buffer_on_full

        self._is_transport_connected = bool(transport)
        self._logger = logger or _logger
        self._prev_connection_error = None
        self._ordering_msg_buffer_counter = itertools.count()
        self._finalized = False

    async def update_transport(self, transport):
        if self._finalized:
            raise InvalidStateError("socket has been finalized")

        if self._is_transport_connected:
            _logger.warning(
                f"!> changing transport while connected current={self.transport}, new={transport=}")

        self._is_transport_connected = True
        self.transport = transport
        # self.connection_restablished.set()
        # self.connection_restablished.clear()

        async with self.connection_restablished:
            self.connection_restablished.notify_all()

    async def __call__(self, data):
        if self._finalized:
            raise FailedToSend("socket has been finalized")

        if not self._is_transport_connected:
            self._logger.debug(f"!> transport not connected buffering data: {data=}")
            return await self._handle_failure(data)

        try:
            self._logger.debug(f"#> sending data using connection: {data=!r}")
            return await self.transport.send(data)
        except ConnectionError as ce:
            self._is_transport_connected = False
            self._prev_connection_error = ce
            return await self._handle_failure(data)

    async def _handle_failure(self, data):
        if not self.use_buffering:
            raise self._prev_connection_error

        future = asyncio.get_running_loop().create_future()
        await self._add_to_buffer(BufferedSend(next(self._ordering_msg_buffer_counter), data, future))
        if self.raise_on_send_failure:
            ftos = FailedToSend(f"transport failed, buffering data: {data=}")
            ftos.item = data
            ftos.future = future
            raise ftos from self._prev_connection_error
        else:
            return await future

    async def _send_buffer(self):
        while not self._finalized:
            async with self.connection_restablished:
                await self.connection_restablished.wait_for(
                    lambda: self._finalized or self._is_transport_connected
                )
            # await self.connection_restablished.wait()

            while not self._finalized:
                buffered_send = await self.buffer.get()
                msg, fut = buffered_send.data, buffered_send.future
                try:
                    if fut.done():
                        self._logger.debug(f"!> dropping cancelled message: {msg=!r}, {fut=!r}")
                        continue
                    self._logger.debug(f"#> sending data using connection: {msg=!r}")
                    fut.set_result(await self.transport.send(msg))
                except OSError:
                    self._is_transport_connected = False
                    await self._add_to_buffer(buffered_send)
                    break
                except AttributeError:
                    # transport is None, and we got \\"None does not have .send"\\ thing
                    self._is_transport_connected = False
                    await self._add_to_buffer(buffered_send)
                    break

    async def _add_to_buffer(self, buffer_send):
        if self._is_buffer_full():
            if not self.should_prune_buffer_on_full:
                raise ValueError("failed buffer is full, cannot add new packet")
            self._prune_buffer()
        await self.buffer.put(buffer_send)
        return buffer_send.future

    def _is_buffer_full(self):
        return self.buffer.full()

    def _prune_buffer(self):
        """Logs a warning and removes the oldest queued message."""
        try:
            buffered_send = self.buffer.get_nowait()
        except asyncio.QueueEmpty:
            return None

        if not buffered_send.future.done():
            ftos = FailedToSend("failed buffer is full, discarding oldest packet")
            ftos.item = buffered_send.data
            buffered_send.future.set_exception(ftos)
        self._logger.warning(
            f"!> discarding socket message {buffered_send}, buffer full",
            exc_info=True,
        )
        return buffered_send.data

    def _may_be_prune_buffer(self):
        """Logs a warning and removes top element from queue"""
        if self._is_buffer_full():
            return self._prune_buffer()
        return None

    def _fail_pending_buffer(self):
        while not self.buffer.empty():
            buffered_msg = self.buffer.get_nowait()
            if buffered_msg.future.done():
                continue
            ftos = FailedToSend("message socket closed before buffered packet was sent")
            ftos.item = buffered_msg.data
            buffered_msg.future.set_exception(ftos)

    @asynccontextmanager
    async def context_manager(self):
        try:
            self._buffer_sender_task = asyncio.create_task(self._send_buffer(),
                                                           name="msg-socket-buffer-sender")
            yield self
        finally:
            if self._finalized:
                self._logger.warning("!> sending message socket already finalized, ignoring __aexit__")
                return

            if not self.buffer.empty():
                self._logger.warning(f"!> failure buffer not empty len={self.buffer.qsize()}")
                self._fail_pending_buffer()

            self._finalized = True
            async with self.connection_restablished:
                self.connection_restablished.notify_all()

            await self._buffer_sender_task
            _logger.debug(f"$> stopped message sender for {self.transport=}")

    def __repr__(self):
        return (
            f"<MessageSocket("
            f"{self.transport}, "
            f"connected={self._is_transport_connected}, "
            f"{'[ordered]' if self.ordering else ''}, "
            f"{'[finalized]' if self._finalized else ''})>"
        )
