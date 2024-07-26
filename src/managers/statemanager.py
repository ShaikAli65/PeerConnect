import asyncio
import functools
import inspect
import math
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from asyncio import Queue as _queue
import threading
from typing import Optional
from src.avails.useables import echo_print
from typing import Iterable


class State:
    def __init__(self, name, func, is_blocking=False, controller=None, event_to_wait: asyncio.Event = None):
        self.name = name

        @functools.wraps(func)
        async def wrap_in_task(_func):
            asyncio.create_task(_func())  # noqa

        @functools.wraps(func)
        def wrap_in_thread(_func):
            threading.Thread(target=func, daemon=True).start()

        self.is_coro = inspect.iscoroutinefunction(func)

        if is_blocking:
            self.func = functools.partial(wrap_in_task if self.is_coro else wrap_in_thread, func)
        else:
            self.func = func

        if inspect.ismethod(func):
            self.func.__func__.__name__ = func.__name__
        else:
            self.func.__name__ = func.__name__

        # self.func_name = func.__name__
        self.actuator = controller
        self.event = event_to_wait

    async def enter_state(self):
        loop = asyncio.get_event_loop()
        x = loop.time()
        echo_print(f"[{x - math.floor(x):.4f}s] entering state :", self.name, end=' ')
        print("func:", self.func.__name__, 'is coro :', self.is_coro)
        if self.is_coro:
            ret_val = await self.func()
        else:
            ret_val = self.func()

        if self.event:
            await self.event.wait()

        return ret_val


class StateManager:
    """
    A Singleton class
    Sort of task queue
    process_states is called at the begining of program
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(StateManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.state_queue = _queue()

        self.executor = _ThreadPoolExecutor()
        self.close = False
        self._initialized = True
        self.last_state = None
        self.global_wait = threading.Event()

    def signal_stopping(self):
        self.close = True
        self.state_queue.put(None)

    async def put_state(self, state: Optional[State]):
        await self.state_queue.put(state)

    async def put_states(self, states: Iterable[State]):
        for state in states:
            await self.state_queue.put(state)

    async def process_states(self):
        """
        Main event loop for the program
        different functions add states to get processed
        """

        while self.close is False:
            current_state: State = await self.state_queue.get()

            await current_state.enter_state()


END_STATE = State('Final State', func=lambda: None)
