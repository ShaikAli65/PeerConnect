import asyncio
import itertools
from asyncio import TaskGroup
from functools import wraps
from typing import Dict, Type, TypeVar

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

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._task_group.__aexit__(exc_type, exc_val, exc_tb)


T = TypeVar('T')


def singleton_mixin(cls: Type[T]) -> Type[T]:
    """Singleton decorator

        Note:
            Not thread safe
    """

    instances: Dict[Type[T], T] = {}

    @wraps(cls)
    def get_instance(*args, **kwargs) -> T:
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance
