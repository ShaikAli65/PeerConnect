import asyncio
import functools
import inspect
import logging
import math
import threading
from asyncio import Queue as _queue
from typing import Iterable, Optional

from src.avails import useables
from src.avails.mixins import singleton_mixin
from src.avails.useables import awaitable

_logger = logging.getLogger(__name__)


def _get_func_name(func):
    """Retrieve the name of a function or callable in a robust way."""
    # Handle partial functions
    if isinstance(func, functools.partial):
        return func.func.__name__

    # Handle bound and unbound methods
    if inspect.ismethod(func):
        return func.__func__.__name__

    # Handle regular functions and callables
    if hasattr(func, "__name__"):
        return func.__name__

    # Fallback to frame inspection if no name is found
    if frame := inspect.currentframe():
        return frame.f_code.co_name

    # Default name if everything else fails
    return "N/A"


class State:
    """Represents a state in application

    Attributes:
        name (str): some detail related to state
        func (Callable): any callable to call when entering state, awaited if it's async
        args(tuple): arguments to pass into function
        is_blocking(bool): True if the function takes long time to complete
        lazy_args(tuple[Callable | Any]): if callable it gets evaluated just before function call or else just passed in, appended to args parameter
        event(asyncio.Event): event to wait before calling func

    """
    def __init__(self, name, func, *args, is_blocking=False, lazy_args=(), event_to_wait: asyncio.Event = None):
        self.name = name
        self.is_blocking = is_blocking
        self.event = event_to_wait
        self.func = func
        self.args = args
        self.lazy_args = lazy_args

    async def _make_function(self):
        func = self.func
        lazy_args = []

        for arg in self.lazy_args:
            if callable(arg):
                result = arg()
                if inspect.isawaitable(result):
                    result = await result
            else:
                result = arg

            lazy_args.append(result)

        self.args += tuple(lazy_args)

        @functools.wraps(func)
        async def wrap_in_task(_func):
            f = useables.wrap_with_tryexcept(_func, *self.args)
            return asyncio.create_task(f())

        @functools.wraps(func)
        def wrap_in_thread(_func):
            threading.Thread(target=func, args=self.args, daemon=True).start()

        self.is_coro = inspect.iscoroutinefunction(func)

        if self.is_blocking:
            self.func = functools.partial(wrap_in_task if self.is_coro else wrap_in_thread, func)
        else:
            self.func = functools.partial(func,*self.args)

        self.func_name = _get_func_name(func)

    async def enter_state(self):
        await self._make_function()

        loop = asyncio.get_event_loop()
        loop_time_ = loop.time() - math.floor(loop.time())
        _logger.info(f"[{loop_time_:.5f}s] [state={self.name}] {{{self.func_name=}}}")

        if self.event:
            await self.event.wait()

        if self.is_coro:
            ret_val = await self.func()
        else:
            ret_val = self.func()

        return ret_val

    def __repr__(self):
        return f"<State({self.name})>"


@singleton_mixin
class StateManager:
    """
    A Singleton class
    Sort of task queue
    process_states is called at the beginning of program
    """

    def __init__(self):
        self.state_queue = _queue()
        self.close = False
        self.all_tasks: list[asyncio.Task] = []

    def signal_stopping(self):
        self.close = True
        self.state_queue.put(None)
        for t in self.all_tasks:
            if not t.done():
                t.cancel("finalizing from state manager")

    async def put_state(self, state: Optional[State]):
        await self.state_queue.put(state)

    async def put_states(self, states: Iterable[State]):
        for state in states:
            # if not isinstance(state, State):
            #     continue
            await self.state_queue.put(state)

    async def process_states(self):
        """
        Main event loop for the program
        different points in code wrap functions in states to get processed
        """
        while self.close is False:
            current_state: State = await self.state_queue.get()
            r = await current_state.enter_state()
            if isinstance(r, asyncio.Task):
                self.all_tasks.append(r)
