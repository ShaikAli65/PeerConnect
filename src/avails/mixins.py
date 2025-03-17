import asyncio
import sys
from asyncio import TaskGroup
from contextlib import AsyncExitStack
from functools import wraps
from typing import Type, TypeVar

from src.avails import HasID, use


class ReplyRegistryMixIn:
    """Provides reply functionality

    Methods:
        msg_arrived: sets the registered future corresponding to expected reply
        register_reply: returns a future that gets set when msg_arrived is called with expected id

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reply_registry = {}

    def msg_arrived(self, message: HasID):
        if not self.is_registered(message):
            return

        fut = self._reply_registry.pop(message.id)
        if not fut.done():
            return fut.set_result(message)

    def register_reply(self, reply_id):
        fut = asyncio.get_running_loop().create_future()
        self._reply_registry[reply_id] = fut
        return fut

    def is_registered(self, message: HasID):
        return str(message.id) in self._reply_registry


class QueueMixIn:
    """
        Requires submit method to exist which should return an awaitable

        Overrides `__call__` method and,
        spawns self.submit as a ``asyncio.Task`` and owns that task lifetime

        Provides context manager that wraps underlying TaskGroup

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._task_group = TaskGroup()

        if not hasattr(self, 'submit'):
            raise ValueError("submit method not found")

    def __call__(self, *args, _task_name=None, **kwargs):
        return self._task_group.create_task(self.submit(*args, **kwargs), name=_task_name)  # noqa

    async def __aenter__(self):
        await self._task_group.__aenter__()
        return self

    def start(self):
        """A handy way to enter task group context synchronously, Useful in constructors """
        use.sync(self._task_group.__aenter__())

    def is_healthy(self):
        async def do_nothing():
            pass

        try:
            self(do_nothing())
            return True
        except RuntimeError:
            return False

    async def repair(self, logger):
        try:
            await self._task_group.__aexit__(None, None, None)
        except ExceptionGroup:
            logger.warning(f"{self.__class__.__name__}, skipping these errors, creating new task group", exc_info=True)

        self._task_group = TaskGroup()
        await self.__aenter__()

    async def _handle_runtime_error(self, logger):
        logger.warning(f"got unexpected runtime error, checking {self.__class__.__name__} queue")
        if self.is_healthy():
            logger.info("requests dispatcher queue healthy")
        else:
            logger.warning("requests dispatcher queue not healthy", exc_info=True)
            logger.debug("recovering...")
            await self.repair(logger)
            logger.debug("recovery done")

    async def __aexit__(self, *exp_details):
        try:
            return await self._task_group.__aexit__(*exp_details)
        except BaseException as exp:
            exp.add_note(f"from {type(self)}")
            raise exp


class AExitStackMixIn:
    """Provides an asynchronous exit stack with name `_exit_stack` """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exit_stack = AsyncExitStack()

    async def __aenter__(self):
        return await self._exit_stack.__aenter__()

    async def __aexit__(self, *exp_details):
        try:
            return await self._exit_stack.__aexit__(*exp_details)  # noqa
        except BaseException as exp:
            exp.add_note(f"from {type(self)}")
            raise exp


class AggregatingAsyncExitStack(AsyncExitStack):
    """An async context manager that aggregates exceptions from nested context managers.

    Extends `AsyncExitStack` to collect all exceptions raised during stack unwinding
    and print them as an `ExceptionGroup`. This ensures all cleanup errors are
    exposed rather than just the first encountered exception.

    Key features:
    - Maintains LIFO order for callback execution
    - Preserves exception context chains
    - Aggregates both sync and async exit exceptions
    - Compatible with standard `AsyncExitStack` API

    Note: This is particularly useful for complex cleanup scenarios where multiple
    resources need to release simultaneously and all errors should be visible.
    """
    __slots__ = ()

    async def __aexit__(self, *exc_details):
        exc = exc_details[1]
        received_exc = exc is not None
        aggregated = []
        if exc is not None:
            aggregated.append(exc)

        frame_exc = sys.exception()

        def _fix_exception_context(_new_exc, old_exc):
            # Walk to the end of the __context__ chain and then hook it to old_exc.
            while True:
                exc_context = _new_exc.__context__
                if exc_context is None or exc_context is old_exc:
                    return
                if exc_context is frame_exc:
                    break
                _new_exc = exc_context
            _new_exc.__context__ = old_exc

        suppressed_exc = False
        pending_raise = False

        # Call callbacks in LIFO order.
        _exit_callbacks = getattr(self, '_exit_callbacks')

        while _exit_callbacks:
            is_sync, cb = _exit_callbacks.pop()
            try:
                current_details = (None, None, None) if exc is None else (type(exc), exc, exc.__traceback__)
                if is_sync:
                    cb_suppress = cb(*current_details)
                else:
                    cb_suppress = await cb(*current_details)
                if cb_suppress:
                    suppressed_exc = True
                    pending_raise = False
                    exc = None
            except BaseException as new_exc:
                _fix_exception_context(new_exc, exc)
                pending_raise = True
                exc = new_exc
                aggregated.append(new_exc)

        if aggregated:
            e = BaseExceptionGroup("Aggregating Multiple exceptions in __aexit__", aggregated)
            # print_exception(e.__class__, e, e.__traceback__)
            raise e

        if pending_raise:
            fixed_ctx = None
            try:
                # bare "raise exc" replaces our carefully
                # set-up context
                fixed_ctx = exc.__context__
                raise exc
            except BaseException:
                exc.__context__ = fixed_ctx
                raise

        return received_exc and suppressed_exc


_T = TypeVar('_T')


def singleton_mixin(cls: Type[_T]) -> Type[_T]:
    """Singleton decorator

        Note:
            Not thread safe
    """

    instance = None  # how to remove this reference in the end ?

    @wraps(cls)
    def get_instance(*args, **kwargs) -> _T:
        nonlocal instance
        if instance is None:
            instance = cls(*args, **kwargs)

        return instance

    return get_instance
