import asyncio
from collections import abc

from tqdm import tqdm


# design decision:
# two things we can provide to transfer API
# 1. A StatusIterator
# 2. A StatusMixIn class that provides functionality to make yield desicions
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
#   calls func: should_yield to make a desicion whether to yield or not
#
#   this requires Transfer classes to work with mix in
# --
#   if (1) is used
#       Then Transfer classes need not be too aware of status updates
#       transfer classes are isolated from the status things and can focus on transferring contents
#       preserving single responsibilty principle

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


class StatusMixIn:
    __slots__ = 'yield_freq', 'current_status', '_yield_iterator', 'progress_bar', 'next_yield_point'

    def __init__(self, yield_freq):
        self.next_yield_point = -1
        self.yield_freq = yield_freq
        self.current_status = 0
        self._yield_iterator = iter(range(yield_freq))
        self.progress_bar = None

    def update_status(self, status):
        self.progress_bar.update(status - self.current_status)
        self.current_status = status

    def should_yield(self):
        if self.current_status > self.next_yield_point:
            self.next_yield_point = next(self._yield_iterator)
            return True
        return False

    def status_setup(self, prefix, initial_limit, final_limit):
        if self.progress_bar:
            self.progress_bar.close()

        self.progress_bar = tqdm(
            range(final_limit),
            desc=prefix,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            # total=initial_limit
        )
        self.progress_bar.update(initial_limit)

        if self.yield_freq < 2:
            self.next_yield_point = final_limit + 1
            self._yield_iterator = None
        else:
            spacing = (final_limit - initial_limit) / (self.yield_freq - 1)
            self._yield_iterator = (min(final_limit, int(initial_limit + i * spacing)) for i in range(self.yield_freq))
            self.next_yield_point = next(self._yield_iterator)

    def close(self):
        if self.progress_bar:
            self.progress_bar.clear()
            self.progress_bar.close()

    def __del__(self):
        self.close()


class StatusIterator(StatusMixIn, abc.AsyncIterable):

    def __aiter__(self):
        return self

    __slots__ = "_queue", "exp"
    _sentinel = object()

    def __init__(self, yield_freq):
        super().__init__(yield_freq)
        self._queue = asyncio.Queue()
        self.exp = self._sentinel

    def update_status(self, status):
        super().update_status(status)
        if self.should_yield():
            self._queue.put(self.current_status)

    async def __anext__(self):
        item = await self._queue.get()

        if item == self._sentinel:
            raise StopAsyncIteration
        elif item == self.exp:
            raise item

        return item

    async def stop(self, any_exp=None):
        """

        Args:
            any_exp: Exception to raise inside async iterator part
                if not provided then *StopAsyncIteration* is raised inside iterator

        """
        self.exp = any_exp or self._sentinel
        await self._queue.put(self.exp)
