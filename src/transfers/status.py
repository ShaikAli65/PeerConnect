import asyncio
from itertools import chain

from tqdm import tqdm

from src.avails.useables import override
from .abc import AbstractStatusIterator, AbstractStatusMix


# design decision:
# two things we can provide to transfer API
# 1. A StatusIterator
# 2. A StatusMixIn class that provides functionality to make yield decisions
# 1.
#
#    class StatusIterator
#       * status_setup(*args)
#       * update(*args)
#       * __anext__
#
#    contains all the necessary information related to frequency of updates
#    uses a queue that gets updated based on the frequency set
#    status_setup function is reentrant and refreshes internal state
#    self contains progress bar
# 2.
#   class StatusMixIn
#       * update(int)
#       * should_yield() -> bool
#
#   calls func: update every time some data is transferred
#   calls func: should_yield to make a decision whether to yield or not
#
#   this requires Transfer classes to work with mix in
# --
#   if (1) is used
#       Then Transfer classes need not be too aware of status updates
#       transfer classes are isolated from the status things and can focus on transferring contents
#       preserving single responsibility principle

#       forcing blocking functions like `start sending or receiving` get spawned as an ``asyncio.Task``
#       further breaking a critical exception control flow in high level handlers
#       cause most of the internal functions are generators with ``async for`` working on them
#       this requires significant refactor
# --
#  if (2) is used
#       Then Transfer classes should work with methods like ``should_yield`` to make a decision.
#       Constructors get clumsy
#       but exception flow is preserved and code can be read in one go
#       helps in making debugging simpler
#  just for the control flow sake we are going with (2)
#  but (1) is still used when multiple generators update a transfer status concurrently


class StatusMixIn(AbstractStatusMix):
    """
    A mixin that tracks progress of a file transfer and provides status updates
    to the user via a tqdm progress bar. Also determines when to yield control
    based on the configured yield frequency.

    This is designed for integration into sender/receiver classes that call
    `update_status()` and use `should_yield()` to determine yield points.

    Args:
        yield_freq (int): Number of yield points desired during the transfer.
    """

    # __slots__ = 'yield_freq', 'current_status', '_yield_iterator', 'progress_bar', 'next_yield_point'

    def __init__(self, yield_freq):
        self.next_yield_point = -1
        self.yield_freq = yield_freq
        self.current_status = 0
        self._yield_iterator = None
        self.progress_bar = None
        self.final_limit = 0  # Track final limit for sentinel

    def update_status(self, status):
        self.progress_bar.update(status - self.current_status)
        self.current_status = status

    def write_update(self, update):
        self.progress_bar.update(update)
        self.current_status += update

    def should_yield(self):
        """
        Check whether the transfer should yield control at this point,
        based on the internal progress and yield frequency.

        Returns:
            bool: True if yielding is appropriate now, False otherwise.
        """
        if self.current_status >= self.next_yield_point:
            try:
                self.next_yield_point = next(self._yield_iterator)
            except StopIteration:
                self.next_yield_point = self.final_limit + 1
            return True
        return False

    def status_setup(self, prefix, initial_limit, final_limit):
        self.final_limit = final_limit
        if self.progress_bar:
            self.progress_bar.close()

        self.progress_bar = tqdm(
            range(final_limit),
            desc=prefix,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            dynamic_ncols=True
        )
        self.progress_bar.update(initial_limit)
        self.current_status = initial_limit

        if self.yield_freq < 1:
            self.next_yield_point = final_limit + 1
            self._yield_iterator = None
        else:
            spacing = (final_limit - initial_limit) / self.yield_freq
            # Generate evenly spaced yield points with rounding
            self._yield_iterator = chain(
                (round(initial_limit + i * spacing) for i in range(1, self.yield_freq + 1)),
                # Add sentinel value to prevent post-completion yields
                [final_limit + 1],
            )
            self.next_yield_point = next(self._yield_iterator)

    def close(self):
        if self.progress_bar:
            self.progress_bar.clear()
            self.progress_bar.close()


class StatusIterator(StatusMixIn, AbstractStatusIterator):
    """
    An asynchronous iterator that yields progress updates during a transfer.
    It wraps `StatusMixIn` and enqueues updates when `should_yield()` returns True.

    Useful when multiple concurrent generators must report progress
    independently but through a shared interface.

    Args:
        yield_freq (int): Number of updates to yield across the transfer.
    """
    __slots__ = "_queue", "exp"
    _sentinel = object()

    def __init__(self, yield_freq):
        super().__init__(yield_freq)
        self._queue = asyncio.Queue()
        self.exp = self._sentinel

    @override
    def update_status(self, status):
        super().update_status(status)
        self._queue.put(self.current_status)

    @override
    def write_update(self, update):
        super().write_update(update)
        self._queue.put(self.current_status)

    def __aiter__(self):
        return self

    async def __anext__(self):
        """
        Async generator interface. Yields next progress update or raises
        StopAsyncIteration or a stored exception to stop iteration.

        Returns:
            int: Current progress value.
        Raises:
            StopAsyncIteration or Exception: If stopped externally.
        """
        item = await self._queue.get()

        if item == self._sentinel:
            raise StopAsyncIteration
        elif item == self.exp:
            raise item

        return item

    async def stop(self, any_exp=None):
        """
        Signals the iterator to stop, optionally raising an exception
        on the next iteration.

        Directly responsible for raising exception in the iterator and is *reentrant*

        Args:
            any_exp (Exception, optional): If provided, this exception is raised
                                           in `__anext__()`. Otherwise, iteration ends.
        """
        self.exp = any_exp or self._sentinel
        await self._queue.put(self.exp)

    @override
    async def close(self):
        await self.stop()
        super().close()
