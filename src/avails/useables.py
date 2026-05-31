from __future__ import annotations

import asyncio
import enum
import functools
import inspect
import logging
import os
import platform
import re
import subprocess
import uuid
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from sys import _getframe  # noqa
from typing import Awaitable, Callable, ParamSpec, TypeVar, override

from src.avails import constants as const

override = override

_logger = logging.getLogger(__name__)


def func_str(func_name):
    return f"{func_name.__name__}()\\{os.path.relpath(func_name.__code__.co_filename)}"


def get_unique_id(_type: type = str, *, u_version="1"):
    id_gen = getattr(uuid, "uuid" + u_version)
    if _type == bytes:
        return id_gen().bytes
    return _type(id_gen())


async def safe_cancel_task(task: asyncio.Task):
    """Cancels task and waits until it returns

    * Handles the case when the parent task gets cancelled and catching that cancelled error misjudges event loop

    * If the task containing this function call gets cancelled then, this function raises cancellation and returns
      irrespective of the completion of `:param task:` (even though it is probably cancelled)

    * Assumes that task will always re-raise the same cancelled error that was passed in, as per asyncio standard
      if not this function does not work as expected

    Notes:
        Make sure that ``task`` is active and not done, if it's result already available then we may get an invalid
        state exception
    Args:
        task(asyncio.Task): task to cancel
    """
    return task.cancel()
    # await _safe_cancel1(task=task)


async def _safe_cancel1(task):
    class CancelFlag(object):
        task_name = None

        def __repr__(self):
            return f"<{self.__class__.__name__}(task_name={self.task_name},id={id(self)})>"

    assert isinstance(task, asyncio.Task), "expected asyncio.Task instance"
    task.cancel(sentinel := CancelFlag())
    sentinel.task_name = task.get_name()

    f = asyncio.shield(task)

    try:
        await asyncio.sleep(0)
        if task.done():
            return

        # it's not a good choice to pass cancelled error of outer function
        # into an already-expected-to-be cancelled task
        return await f  # wait until return
    except asyncio.CancelledError as ce:
        curr = asyncio.current_task()
        if not task.done():
            # this means `ce` is not raised by completion of task
            # and `ce` belongs to current task
            raise ce

        try:
            # we lose our sentinel inside shield as it plays cleverly with futures
            task.exception()  # unwrap
        except asyncio.CancelledError as ce_task:
            if sentinel in ce_task.args:
                if curr.cancelling():
                    # edge case where task gets done immediately after cancellation
                    # and `ce` belongs to current task
                    raise ce
                return


def shorten_path(path: Path, max_length):
    if len(str(path)) <= max_length:
        return str(path)
    selected_parts = list(path.parts)
    part_ptr = 1
    while len("".join(selected_parts)) >= max_length:
        if len(selected_parts) <= 2:
            break
        selected_parts.pop(part_ptr)

    selected_parts.insert(1, '..')
    return os.path.sep.join(selected_parts)


def get_timeouts(initial=0.001, factor=2, max_retries=const.MAX_RETIRES, max_value=5.0):
    """
    Generate exponential backoff timeout values.

    Args:
        initial (float): The initial timeout value in seconds. Defaults to 0.001.
        factor (int): The factor by which the timeout value is multiplied at each step. Defaults to 2.
        max_retries (int): The maximum number of retries. Defaults to 5, if -1 is provided then yields infinitely
        max_value (float): The maximum timeout value in seconds. Defaults to 5.0.

    Yields:
        float: The next timeout value in the sequence, capped by max_value.

    Example:
        >>> list(get_timeouts())
        [0.001, 0.002, 0.004, 0.008, 0.016]

        >>> list(get_timeouts(initial=1, factor=3, max_retries=4, max_value=10))
        [1, 3, 9, 10]
    """
    current = initial

    if max_retries == -1:
        while True:
            if current >= max_value:
                yield max_value
            current *= factor

    for _ in range(max_retries):
        yield min(current, max_value)
        current *= factor


async def async_timeouts(*, initial=0.001, factor=2, max_retries=const.MAX_RETIRES, max_value=5.0):
    """
    same as :func: `get_timeouts` but delays itself in yielding, first yield is immediate

    Example::

        async for _ in async_timeouts(initial=1, factor=2, max_retries=4, max_value=5):
            # any working code that needs to be executed with delays

    Yields:
        None
    """

    yield

    for timeout in get_timeouts(initial, factor, max_retries, max_value):
        await asyncio.sleep(timeout)
        yield


async def async_input(helper_str=""):
    try:
        return await asyncio.to_thread(input, helper_str)
    except EOFError:
        return None


def open_file(content):
    if platform.system() == "Windows":
        powershell_script = f"""
        $file = '{content}'
        Invoke-Item $file
        """
        result = subprocess.run(["powershell.exe", "-Command", powershell_script], stdout=subprocess.PIPE,
                                text=True)
        return result.stdout.strip()
    elif platform.system() == "Darwin":
        subprocess.run(["open", content])
    else:
        subprocess.run(["xdg-open", content])
    return None


_CO_NESTED = inspect.CO_NESTED
_CO_FROM_COROUTINE = inspect.CO_COROUTINE | inspect.CO_ITERABLE_COROUTINE | inspect.CO_ASYNC_GENERATOR


def from_coroutine(level=2, _cache={}):  # noqa
    f_code = _getframe(level).f_code
    if f_code in _cache:
        return _cache[f_code]
    if f_code.co_flags & _CO_FROM_COROUTINE:
        _cache[f_code] = True
        return True
    else:
        if f_code.co_flags & _CO_NESTED and f_code.co_name[0] == '<':
            return from_coroutine(level + 2)
        else:
            _cache[f_code] = False
            return False


def sync(coro):
    """Sync hack to coro
    As coroutines are iterators internally so it's fine

    Note:
        works only if there is not much awaiting happening within coro
        Don't pass asyncio.Future, it is clever ;)

    Args:
        coro: coroutine that needs to be completed on
    """
    try:
        return coro.send(None)
    except StopIteration as si:
        return si.value


P = ParamSpec("P")
R = TypeVar("R")


def awaitable(syncfunc: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    """
    # this uses code from curio package

    Author : Dabeaz
    Repo : https://github.com/dabeaz/curio

    Decorator that allows an asynchronous function to be paired with a
    synchronous function in a single function call.  The selection of
    which function executes depends on the calling context.  For example:

        def spam(sock, maxbytes):                       (A)
            return sock.recv(maxbytes)

        @awaitable(spam)                                (B)
        async def spam(sock, maxbytes):
            return await sock.recv(maxbytes)

    In later code, you could use the spam() function in either a synchronous
    or asynchronous context.  For example:

        def foo():
            ...
            r = spam(s, 1024)          # Calls synchronous function (A) above
            ...

        async def bar():
            ...
            r = await spam(s, 1024)    # Calls async function (B) above
            ...

    """

    def decorate(asyncfunc):
        @functools.wraps(asyncfunc)
        def wrapper(*args, **kwargs):
            if from_coroutine():
                return asyncfunc(*args, **kwargs)
            else:
                return syncfunc(*args, **kwargs)

        wrapper._syncfunc = syncfunc
        wrapper._asyncfunc = asyncfunc
        wrapper._awaitable = True
        wrapper.__doc__ = syncfunc.__doc__ or asyncfunc.__doc__
        return wrapper

    return decorate


class COLORS(enum.StrEnum):
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"


def wrap_with_tryexcept(func, *args, _logger=_logger, **kwargs):
    """
    Designed to use like:

    >>> f = wrap_with_tryexcept(func, *args, **kwargs)
    >>> asyncio.create_task(f())  # sort of `functools.partial` aesthetics

    Swallows Exception and logs them, basically stopping the exeception from propagating to the caller
    Best used for async functions running in a TaskGroup where we don't want to cancel the whole group

    Args:
        _logger: An Optional logger to log exceptions
        func : any async function
        args, kwargs : to forward

    """

    @functools.wraps(func)
    async def wrapped_with_tryexcept():
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            _logger.exception(
                f"got an exception for function {func_str(func)} : {type(e)} : {e}",
                stack_info=True
            )

    return wrapped_with_tryexcept


def keep_task_reference(func):
    """Decorator
    Event does not hold a reference to running tasks, to prevent task disappearing
    in the middle of its execution, this keeps a strong reference to current running task
    """

    @wraps(func)
    def task_wrapper(*args, **kwargs):
        _ = asyncio.current_task()
        return func(*args, **kwargs)

    return task_wrapper


class NotInUse:
    __annotations__ = {
        'function': str,
        '__doc__': str
    }
    __slots__ = 'function', '__doc__'

    def __init__(self, function):
        """Decorator class to mark functions as not in use or not fully tested.

        Used to mark functions that are not currently in use or haven't been fully tested.
        By marking a function with this class, it prevents the call to the function unless explicitly allowed by the user.

        Args:
            function: The function to be decorated.

        Raises:
            ValueError : if function gets called
        """
        self.function = function

    def __call__(self, *args, **kwargs):
        """
        Args:
        - *args: Positional arguments for the function.
        - **kwargs: Keyword arguments for the function.
        """
        raise ValueError(f"Your are not supposed to call this function :{self.function.__name__}")


def camel_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class Lock(asyncio.Lock):
    def __str__(self):
        return f"<Lock(locked={self.locked()})>"

    def __repr__(self):
        return str(self)


provide__init__ = dataclass
