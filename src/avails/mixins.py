import asyncio
import functools
import inspect
import logging
import reprlib
import sys
from asyncio import CancelledError, TaskGroup
from contextlib import AsyncExitStack
from functools import wraps
from inspect import isawaitable
from typing import TYPE_CHECKING, Type, TypeVar

from src.avails import BaseDispatcher, HasID, use

_logger = logging.getLogger(__name__)


class ReplyRegistryMixIn:
    """Provides reply functionality

    Methods:
        reply_arrived: sets the registered future corresponding to expected reply
        register_reply: returns a future that gets set when reply_arrived is called with expected id

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reply_registry = {}

    def reply_arrived(self, message: HasID):
        if not self.is_registered(message):
            return None

        fut = self._reply_registry.pop(message.id)
        if not fut.done():
            return fut.set_result(message)
        loop = asyncio.get_running_loop()
        loop.call_soon(self.__prune_done_futures, self._reply_registry)
        return None

    @staticmethod
    def __prune_done_futures(container):
        removes = []
        append = removes.append
        for msg_id, fut in container.items():
            if fut.done():
                append(msg_id)

        for msg_id in removes:
            container.pop(msg_id)

    def register_reply(self, reply_id):
        fut = asyncio.get_running_loop().create_future()
        self._reply_registry[reply_id] = fut
        return fut

    def is_registered(self, message: HasID):
        return str(message.id) in self._reply_registry


class TaskGroupMixIn:
    """Calls made to `__call__` are spawned as tasks using an internal TaskGroup

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
            logger.warning(f"{self.__class__.__name__}, skipping these errors, creating new task group",
                           exc_info=True)

        self._task_group = TaskGroup()
        await self.__aenter__()

    async def _handle_runtime_error(self, logger):
        logger.warning(f"got unexpected runtime error, checking {self.__class__.__name__} queue")
        logger.debug("", exc_info=True)
        if self.is_healthy():
            logger.info("requests dispatcher queue healthy, raise error again")
            raise
        else:
            logger.warning("requests dispatcher queue not healthy", exc_info=True)
            logger.debug("recovering...")
            await self.repair(logger)
            logger.debug("recovery done")

    async def __aexit__(self, *exp_details):
        try:
            return await self._task_group.__aexit__(*exp_details)
        except CancelledError:
            return None
        except ExceptionGroup as exp:
            exp.add_note(f"from {type(self)}")
            raise exp


class CallHandlerMixIn:
    if TYPE_CHECKING:
        registry: dict

    async def call_handler(self, header, *args, _logger, **kwargs):
        try:
            handler = self.registry[header]
        except KeyError:
            _logger.error(f"{self._log_prefix} {self.__class__} no handler found for event {header=}")
            return None

        try:
            r = handler(*args, **kwargs)
            if isawaitable(r):
                return await asyncio.ensure_future(r)
            return r
        except RuntimeError:
            if hasattr(self, '_handle_runtime_error'):
                return await self._handle_runtime_error(_logger)
            return None
        except Exception as exp:
            # we can't afford exceptions here as they move into TaskGroupMixIn
            return _logger.exception(
                f"{self._log_prefix} {handler}({args=},{kwargs=}) failed with: \n", exc_info=exp
            )

    @property
    def _log_prefix(self):
        return f"{self.__class__}"


class AExitStackMixIn:
    """Provides an asynchronous exit stack with attribute ``_exit_stack`` """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exit_stack = AsyncExitStack()
        self._exiting = False

    async def __aenter__(self):
        return await self._exit_stack.__aenter__()

    async def __aexit__(self, *exp_details):
        if self._exiting:
            return None
        self._exiting = True
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

    def print_exit_callbacks(self, *, file=None, include_closure=True):
        """Print a structured view of registered exit callbacks.

        The output is intentionally diagnostic: it uses CPython's private
        ``_exit_callbacks`` storage because that is where ``AsyncExitStack``
        keeps the registered ``__exit__``/``__aexit__`` wrappers. This method
        only reads the deque and does not change unwind order.
        """
        file = file or sys.stdout
        exit_callbacks = list(getattr(self, '_exit_callbacks', ()))
        print(
            f"{self.__class__.__name__} exit callbacks "
            f"(count={len(exit_callbacks)}, order=LIFO/unwind order)",
            file=file,
        )

        if not exit_callbacks:
            print("  <empty>", file=file)
            return

        total = len(exit_callbacks)
        for unwind_index, (is_sync, callback) in enumerate(reversed(exit_callbacks), 1):
            registered_index = total - unwind_index
            print(f"\n[{unwind_index}] registered_index={registered_index}", file=file)
            details = self._describe_exit_callback(
                callback,
                is_sync=is_sync,
                include_closure=include_closure,
            )
            self._print_structured(details, file=file, indent=2)

    @classmethod
    def _describe_exit_callback(cls, callback, *, is_sync, include_closure):
        details = {
            "exit_type": "sync __exit__/callback" if is_sync else "async __aexit__/callback",
            "callback": cls._describe_callable(callback, include_closure=include_closure),
        }

        wrapped = getattr(callback, "__wrapped__", None)
        if wrapped is not None:
            details["wrapped_callback"] = cls._describe_callable(
                wrapped,
                include_closure=False,
            )

        if inspect.ismethod(callback):
            details["bound_method"] = {
                "self": cls._describe_object(callback.__self__),
                "function": cls._describe_callable(
                    callback.__func__,
                    include_closure=include_closure,
                ),
            }

        if isinstance(callback, functools.partial):
            details["partial"] = cls._describe_partial(callback, include_closure=include_closure)

        return details

    @classmethod
    def _describe_callable(cls, callback, *, include_closure):
        unwrapped = inspect.unwrap(callback)
        details = {
            "object_type": cls._type_name(callback),
            "module": getattr(callback, "__module__", None),
            "qualname": getattr(callback, "__qualname__", None),
            "name": getattr(callback, "__name__", None),
            "source": cls._source_location(unwrapped),
        }

        if unwrapped is not callback:
            details["unwrapped"] = {
                "module": getattr(unwrapped, "__module__", None),
                "qualname": getattr(unwrapped, "__qualname__", None),
                "source": cls._source_location(unwrapped),
            }

        if include_closure:
            closure = cls._closure_details(callback)
            if closure:
                details["closure"] = closure

        return details

    @classmethod
    def _describe_partial(cls, callback, *, include_closure):
        return {
            "func": cls._describe_callable(
                callback.func,
                include_closure=include_closure,
            ),
            "args": [cls._safe_repr(arg) for arg in callback.args],
            "keywords": {
                key: cls._safe_repr(value)
                for key, value in (callback.keywords or {}).items()
            },
        }

    @classmethod
    def _closure_details(cls, callback):
        try:
            closure_vars = inspect.getclosurevars(callback)
        except TypeError:
            return {}

        details = {}
        if closure_vars.nonlocals:
            details["nonlocals"] = {
                key: cls._safe_repr(value)
                for key, value in closure_vars.nonlocals.items()
            }
        if closure_vars.globals:
            details["globals"] = sorted(closure_vars.globals)
        if closure_vars.unbound:
            details["unbound"] = sorted(closure_vars.unbound)
        return details

    @classmethod
    def _describe_object(cls, obj):
        return {
            "object_type": cls._type_name(obj),
            "module": getattr(obj, "__module__", None),
            "class": cls._type_name(type(obj)),
        }

    @staticmethod
    def _source_location(callback):
        try:
            source_file = inspect.getsourcefile(callback) or inspect.getfile(callback)
        except TypeError:
            return None

        try:
            _, start_line = inspect.getsourcelines(callback)
        except (OSError, TypeError):
            start_line = None

        if source_file is None:
            return None
        if start_line is None:
            return source_file
        return f"{source_file}:{start_line}"

    @staticmethod
    def _safe_signature(callback, *, follow_wrapped=True):
        try:
            return str(inspect.signature(callback, follow_wrapped=follow_wrapped))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_repr(obj):
        try:
            return reprlib.repr(obj)
        except Exception as exp:
            return f"<repr failed: {type(exp).__name__}: {exp}>"

    @staticmethod
    def _type_name(obj):
        typ = obj if isinstance(obj, type) else type(obj)
        return f"{typ.__module__}.{typ.__qualname__}"

    @classmethod
    def _print_structured(cls, value, *, file, indent):
        prefix = " " * indent
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (dict, list, tuple)):
                    print(f"{prefix}{key}:", file=file)
                    cls._print_structured(item, file=file, indent=indent + 2)
                else:
                    print(f"{prefix}{key}: {item}", file=file)
            return

        if isinstance(value, (list, tuple)):
            if not value:
                print(f"{prefix}[]", file=file)
                return
            for item in value:
                if isinstance(item, (dict, list, tuple)):
                    print(f"{prefix}-", file=file)
                    cls._print_structured(item, file=file, indent=indent + 2)
                else:
                    print(f"{prefix}- {item}", file=file)
            return

        print(f"{prefix}{value}", file=file)

    async def __aexit__(self, *exc_details):
        if any(exc_details):
            _logger.error(f"error {exc_details=}", exc_info=True)
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


Dispatcher = TaskGroupMixIn, ReplyRegistryMixIn, CallHandlerMixIn, BaseDispatcher

BasicDispatcher = TaskGroupMixIn, CallHandlerMixIn, BaseDispatcher

# Usage::
# class SomeDispatcher(*BasicDispatcher):
#    pass

# We are using `Dispatcher`, `BasicDispatcher` as tuples  
# instead of something like this::
#
# class Dispatcher(TaskGroupMixIn, ReplyRegistryMixIn, CallHandlerMixIn, BaseDispatcher):
#     __slots__ = ()
#
# class BasicDispatcher(TaskGroupMixIn, CallHandlerMixIn, BaseDispatcher):
#     __slots__ = ()

# Cause we can get rid of a mro level just by using `*` (unpack) while defining class
#
# previous::
#
# class SomeDispatcher(BasicDispatcher):
#    pass
#
# now::
#
# class SomeDispatcher(*BasicDispatcher):
#    pass
# this is important cause dispatchers are core to the application and have lots of calls to them
# i didn't ran some benchmarks, just doing it in a different way ;)

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
