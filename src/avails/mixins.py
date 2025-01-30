import asyncio
import sys

from asyncio.futures import _chain_future  # noqa  # a little bit dirty to use internal APIs but it's needed

if sys.version_info >= (3, 13):
    from asyncio import CancelledError
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

        Provides context manager that throws a cancelled error into all the remaining tasks
        and waits for completion on those tasks

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_group = set()

    def __call__(self, *args, **kwargs):

        if hasattr(self, 'submit'):
            f = asyncio.create_task(self.submit(*args, **kwargs))
            f.set_name(f"{self.__class__}, task at {QueueMixIn}")
            self.task_group.add(f)
            f.add_done_callback(lambda _fut: self.task_group.remove(_fut))
            return f
        else:
            raise ValueError("submit method not found")

    async def stop(self):
        for task in self.task_group:
            task.cancel()

        await asyncio.sleep(0)

        exceptions = []
        for task in asyncio.as_completed(self.task_group):
            try:
                await task
            except CancelledError:
                pass
            except Exception as e:
                exceptions.append(e)

        raise ExceptionGroup(f"exceptions at {QueueMixIn}({self.__class__})", exceptions)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
