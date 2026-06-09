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
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar, override

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


async def safe_cancel(task: asyncio.Task):
    """Cancels ``task`` and waits until it is fully done.

    Correctly handles the case where the calling task is also cancelled concurrently,
    without suppressing that external cancellation.

    If the task containing this function call gets cancelled then, this function raises cancellation and returns
    without waiting for the given task to finish, or cleanup.

    This function will collect the error of the given task properly maintaining the clean up, for a
    different behaviour when error collection is not needed, see `cancel_and_wait`

    Note:
        Assumes that task will always re-raise the same cancelled error that was passed
        in (as per asyncio standard). otherwise this function does not work as expected

    Args:
        task: an asyncio.Task that is not yet done; call task.done() before this if unsure.
    """
    __tracebackhide__ = True

    @provide__init__
    class CancelFlag:
        task_name: str

        def __repr__(self):
            return f"<{self.__class__.__name__}(task_name={self.task_name}, id={id(self)})>"

    assert isinstance(task, asyncio.Task), "expected asyncio.Task instance"

    # Nothing to do — also avoids the InvalidStateError that task.cancel() raises on a
    # finished task.
    if task.done():
        return

    # Request cancellation unconditionally.
    # _safe_cancel1 returned early when task.cancelling() > 0, which skipped the wait.
    # We still call cancel() here even if a cancellation is already in-flight: it is
    # idempotent from the task's perspective (increments the internal counter by 1) and
    # ensures the task will stop even if the earlier cancel was somehow swallowed.
    task.cancel(sentinel := CancelFlag(task_name=task.get_name()))

    try:
        # Yield once so the event loop can deliver the CancelledError into task.
        # Fast path: cooperative tasks that cancel immediately are done after this yield.
        await asyncio.sleep(0)
        if task.done():
            return

        # Wait for task to finish, but without forwarding any *external* cancellation
        # that arrives on the calling task.
        #
        # Without shield: if this coroutine's own task is cancelled externally while we
        # are waiting, asyncio would forward that CE into `task` as an extra task.cancel()
        # call — a second, unintended cancellation.  asyncio.shield() breaks this by
        # creating a separate outer future that absorbs the external CE, leaving `task`
        # itself undisturbed so it can finish on its own schedule.
        await asyncio.shield(task)

    except asyncio.CancelledError as ce:
        # A CancelledError reaches here from exactly two sources:
        #
        #   (A) task finished with cancellation — shield propagates the inner task's
        #       cancelled state to the outer future, which then raises CE here.
        #
        #   (B) the calling coroutine's own task was cancelled externally — asyncio
        #       throws a CE at the nearest suspension point (the shield await).
        #
        # task.done() is the correct discriminator:
        # shield only propagates the inner task's result *after* task has fully completed,
        # so if task is not done the CE cannot have come from source (A).

        if not task.done():
            # Source (B) only: our task is being cancelled while task is still running.
            # task.cancel() was already called above, so task will finish on its own.
            # We must not suppress our own task's cancellation — re-raise immediately.
            raise ce.with_traceback(None)

        # task IS done. The CE may have come from (A), (B), or both arriving together.
        #
        # curr.cancelling() > 0 means the calling task has at least one pending external
        # cancel request outstanding.  We must re-raise in that case, regardless of how
        # task finished (cancelled, returned normally, or raised another exception).
        if asyncio.current_task().cancelling():
            raise ce.with_traceback(None)

        # task is done and there is no outstanding cancellation on the calling task.
        # The CE came from source (A) only: task's cancellation propagated through shield.
        # This is the normal success path — swallow the CE and return.
        # with a assurance check that CE contains the exception we put into the task
        if sentinel not in ce.args:
            raise ce.with_traceback(None)  # this is something else than our own cancellation


async def cancel_and_wait(task: asyncio.Task[Any]):
    """Cancel the *fut* future or task and wait until it completes."""

    def _release_waiter(*args):
        if not waiter.done():
            waiter.set_result(None)

    loop = asyncio.get_running_loop()
    waiter = loop.create_future()
    task.add_done_callback(_release_waiter)

    try:
        task.cancel()
        # We cannot wait on *task* directly to make
        # sure _cancel_and_wait itself is reliably cancellable.
        await waiter
    finally:
        task.remove_done_callback(_release_waiter)


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
                stack_info=True,
                stacklevel=2,
            )

    return wrapped_with_tryexcept


def keep_task_reference(func):
    """Decorator

    Event loop does not hold a reference to running tasks, to prevent task disappearing
    in the middle of its execution, this keeps a strong reference to current running task
    """

    @wraps(func)
    def task_wrapper(*args, **kwargs):
        _ = asyncio.current_task()
        return func(*args, **kwargs)

    return task_wrapper


def run_background_task(coro, name, app_exit_stack, *, cleanup_on_exit=True):
    """
    Run a coroutine as a background task with optional cleanup on exit.

    This function creates an asyncio Task from the given coroutine and optionally
    registers it with an application-level exit stack for proper cleanup. The task
    can be canceled either asynchronously or synchronously based on the specified
    parameters.

    Parameters:
        coro (Coroutine): The coroutine to be run as a background task.
        name (str): A name for the asyncio Task to aid debugging.
        app_exit_stack (AsyncExitStack): The exit stack used to manage application-level
            cleanup.
        cleanup_on_exit (bool): Whether to perform safe cleanup on application exit.
            If True, the task will be canceled asynchronously using a registered
            callback. Defaults to True.

    Returns:
        asyncio.Task: The created asyncio Task running the provided coroutine.
    """

    t = asyncio.create_task(coro, name=name)
    if cleanup_on_exit:
        app_exit_stack.push_async_callback(safe_cancel, t)
    else:
        app_exit_stack.push_async_callback(cancel_and_wait, t)
    return t


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
