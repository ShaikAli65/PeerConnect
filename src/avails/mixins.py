import asyncio
import sys

from asyncio.futures import _chain_future  # noqa  # a little bit dirty to use internal APIs but it's needed

if sys.version_info >= (3, 13):
    from asyncio import QueueShutDown
else:
    class QueueShutDown(Exception):
        ...

from src.avails import HasID, HasIdProperty
from src.avails.exceptions import DispatcherFinalizing


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
        return fut.set_result(message)

    def register_reply(self, reply_id):
        fut = asyncio.get_running_loop().create_future()
        self._reply_registry[reply_id] = fut
        return fut


class QueueMixIn:
    """Provides a CSP(`Communicating Sequential Processes`) way to submit event to the Dispatcher classes

    Adds an extra function ``listen_for_events`` that needs to get started as a task to start listening
    for events.

    Overrides __call__ method of ``dispatcher`` object and submits that event to queue,
    this allows to call ``:func BaseDispatcher.submit:`` directly if needed.

    Requires the ``stop_flag`` attribute as a callable that should return a boolean
    signaling stopping of event listening loop

    If used, this class should come early in mro

    If an event is submitted then a call to function ``submit`` is made, and it is spawned as an ``asyncio.Task``
    using an internal ``asyncio.TaskGroup``, submit function should return without any exception
    Internal queue does not have any limits,

    if ``:param start_listening:`` is true then stop method takes care of cancelling it

    A stop method is provided, which
        * cancels internal queue to end the processing
        * stops the **queue**, does not discard buffered events waits for completion
        * cancels taskgroup(as mentioned in python docs) by raising a `DispatcherFinalizing` exception
        * if ``:func listener_task:`` is then it is also cancelled


    Attributes:
        queue (asyncio.Queue): internal queue that is used to receive events
        task_group (asyncio.TaskGroup): used to spawn tasks
        running(bool): gets set to true when ``:func listen_for_events:`` is called
    """
    _sentinel = object()

    def __init__(self, *args, start_listening=True, **kwargs):
        """
        Args:
            start_listening (bool):
                an optional argument which specifies : should it start the `listen_for_events` as
                a task or not, default is true
        """
        super().__init__(*args, **kwargs)
        self._queue = asyncio.Queue()
        self.task_group = asyncio.TaskGroup()
        self.__running = False
        self.listener_task = None
        if start_listening:
            self.listener_task = asyncio.create_task(self.listen_for_events())

    def __call__(self, *args, **kwargs):
        fut = asyncio.get_running_loop().create_future()
        self._queue.put_nowait((fut, args, kwargs))
        return fut

    async def listen_for_events(self):
        stop_flag = self.stop_flag  # noqa
        que = self._queue
        self.__running = True
        async with self.task_group:
            while True:
                try:
                    fut, args, kwargs = await que.get()
                    if fut == self._sentinel:
                        raise QueueShutDown()

                except QueueShutDown:
                    break

                if stop_flag():
                    break
                t = self.task_group.create_task(self.submit(*args, **kwargs))  # noqa
                _chain_future(t, fut)

    async def stop(self):
        async def bomb():
            raise DispatcherFinalizing('stop method is called for dispatcher')

        self.task_group.create_task(bomb())
        if sys.version_info >= (3, 13):
            self._queue.shutdown()
        else:
            await self._queue.put((self._sentinel,) * 3)
        self.__running = False
        if self.listener_task:
            self.listener_task.cancel()
            await asyncio.sleep(0)  # allowing all the things to happen before waiting on listener_task
            await self.listener_task

    async def __aenter__(self):
        if self.__running is True:
            return

        if self.listener_task is None:
            self.listener_task = asyncio.create_task(self.listen_for_events())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.__running is False:
            return

        await self.stop()
        await self.task_group.__aexit__(exc_type, exc_val, exc_tb)
