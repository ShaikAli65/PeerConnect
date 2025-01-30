import asyncio
import sys

from asyncio.futures import _chain_future  # noqa  # a little bit dirty to use internal APIs but it's needed

if sys.version_info >= (3, 13):
    from asyncio import TaskGroup
else:
    class QueueShutDown(Exception):
        ...

from src.avails import HasID, HasIdProperty


class ReplyRegistryMixIn:
    """Provides reply functionality

    Methods:
        msg_arrived: sets the registered future corresponding to expected reply
        register_reply: returns a future that gets set when msg_arrived is called with expected id

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reply_registry = {}

    def msg_arrived(self, message: HasID | HasIdProperty):
        if message.id not in self._reply_registry:
            return

        fut = self._reply_registry.pop(message.id)
        if not fut.done():
            return fut.set_result(message)

    def register_reply(self, reply_id):
        fut = asyncio.get_running_loop().create_future()
        self._reply_registry[reply_id] = fut
        return fut


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

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._task_group.__aexit__(exc_type, exc_val, exc_tb)
