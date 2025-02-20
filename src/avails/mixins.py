import asyncio
import itertools
import sys
from asyncio import TaskGroup
from contextlib import AsyncExitStack
from functools import wraps
from typing import Type, TypeVar

from src.avails import HasID, use


class ReplyRegistryMixIn:
    """Provides reply functionality

    an id_factory is provided that can be used to set a unique id to messages

    Methods:
        msg_arrived: sets the registered future corresponding to expected reply
        register_reply: returns a future that gets set when msg_arrived is called with expected id

    """

    _id_factory = itertools.count()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reply_registry = {}

    def msg_arrived(self, message: HasID):
        if message.id not in self._reply_registry:
            return

        fut = self._reply_registry.pop(message.id)
        if not fut.done():
            return fut.set_result(message)

    def register_reply(self, reply_id):
        fut = asyncio.get_running_loop().create_future()
        self._reply_registry[reply_id] = fut
        return fut

    def is_registered(self, message: HasID):
        return message.id in self._reply_registry

    @property
    def id_factory(self):
        return str(next(self._id_factory))


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

    def __call__(self, *args, **kwargs):
        return self._task_group.create_task(self.submit(*args, **kwargs))  # noqa

    async def __aenter__(self):
        await self._task_group.__aenter__()
        return self

    def start(self):
        """A handy way to enter task group context synchronously, Useful in constructors """
        use.sync(self._task_group.__aenter__())

    async def __aexit__(self, *exp_details):
        return await self._task_group.__aexit__(*exp_details)


class AExitStackMixIn:
    """Provides an asynchronous exit stack with name `_exit_stack` """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exit_stack = AsyncExitStack()

    async def __aenter__(self):
        return await self._exit_stack.__aenter__()

    async def __aexit__(self, *exp_details):
        return await self._exit_stack.__aexit__(*exp_details)  # noqa


class _AggregatingAsyncExitStack(AsyncExitStack):
    """As the name says, aggregates all the exceptions raised by context managers, and raises an ExceptionGroup

    Most of the code is just a copy and paste from stdlib
    Just modified to aggregate exceptions
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
        _exit_callbacks = getattr(self,'_exit_callbacks')

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

        if pending_raise and aggregated:
            raise ExceptionGroup("Multiple exceptions in __aexit__", aggregated)

        return received_exc and suppressed_exc


class AsyncMultiContextManagerMixIn:
    """Helps in maintaining all the contexts of classes with multiple inheritance

    Should come early in MRO if used, so that it can control the exit hierarchy

    Useful when we need to enter and exit all the classes with exception propagation in-place

    This is helpful when we have multiple exits and all the classes need not be aware of super class's exit method

    No need to do this::

        class B:
            async def __aexit__(self, *args):
                print("B aexit")
                if hasattr(super(),'__aexit__'):
                    super().__aexit__(*args)
                ### this needs to be done in all the exits

    Examples:

    ::

        class B:
            async def __aenter__(self):
                print("B aenter")
            async def __aexit__(self, exc_type, exc_value, traceback):
                print("B aexit")
                # No exception here; simply return False.
                return False

        class C:
            async def __aenter__(self):
                print("C aenter")
            async def __aexit__(self, exc_type, exc_value, traceback):
                print("C aexit")
                raise ValueError("C failed on aexit")

        class D:
            async def __aenter__(self):
                print("D aenter")
            async def __aexit__(self, exc_type, exc_value, traceback):
                print("D aexit")
                raise ValueError("D failed on aexit")

        class E(AsyncMultiContextManagerMixIn, B, C, D):
            pass
        # this ensures that all the B,C,D classes cleanup perfectly

    Raises:
        ExceptionGroup: aggregates all the exceptions, so that we can get tracebacks

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aexit_stack = _AggregatingAsyncExitStack()

    async def __aenter__(self):
        await self._aexit_stack.__aenter__()

        # Walk the MRO (excluding this mixin) and for each class:
        # 1. Register its __aexit__ (if any) with push_async_callback.
        # 2. Call its __aenter__ (if any).

        mro = type(self).mro()
        mro.remove(AsyncMultiContextManagerMixIn)
        # two ways to reach here
        # 1. subclass does not have aenter
        # 2. subclass used super call in it's aenter method
        # in both of the cases no need to re-enter subclass's context again (we get recursion if we are lucky enough)
        mro.remove(type(self))

        for cls in mro:
            aexit_method = cls.__dict__.get("__aexit__")
            if aexit_method:
                # Capture the current aexit_method in the lambda default argument to prevent late binding.
                self._aexit_stack.push_async_exit(
                    lambda *args, exit_method=aexit_method: exit_method(self, *args)  # noqa
                )
            aenter_method = cls.__dict__.get("__aenter__")
            if aenter_method:
                result = aenter_method(self)
                if asyncio.iscoroutine(result):
                    await result
        return self

    async def __aexit__(self, *args):
        """Delegates all __aexit__ calls to the internal ExitStack for proper handling."""
        return await self._aexit_stack.__aexit__(*args)


T = TypeVar('T')


def singleton_mixin(cls: Type[T]) -> Type[T]:
    """Singleton decorator

        Note:
            Not thread safe
    """

    instance = None  # how to remove this reference in the end ?

    @wraps(cls)
    def get_instance(*args, **kwargs) -> T:
        nonlocal instance
        if instance is None:
            instance = cls(*args, **kwargs)

        return instance

    return get_instance
