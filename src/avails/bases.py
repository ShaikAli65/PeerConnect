import asyncio
import enum
import sys
from abc import ABC, abstractmethod
from typing import Callable, NamedTuple

if sys.version_info >= (3, 13):
    from asyncio import QueueShutDown
else:
    class QueueShutDown(Exception):
        ...

from src.avails import GossipMessage
from src.avails.events import RequestEvent
from src.avails.exceptions import DispatcherFinalizing


class QueueMixIn:
    """Provides a CSP(`Communicating Sequential Processes`) way to submit event to the Dispatcher classes

    Adds an extra function ``listen_for_events`` that needs to get started as a task to start listening
    for events.
    Overides __call__ method of ``dispatcher`` object and submits that event to queue,
    this allows to call ``:func BaseDispatcher.submit:`` directly if needed.

    If used this class should come early in mro

    If an event is submitted then a call to function ``submit`` is made and it is spawned as an ``asyncio.Task``
    using an internal ``asyncio.TaskGroup``, submit function should return without any exception

    Internal queue does not have any limits,

    if ``:param start_listening:`` is true then stop method takes care of cancelling it

    A stop method is provided, which
        * cancels internal queue to end the processing
        * stops the **queue**, does not discarding buffered events waits for completion
        * cancels taskgroup(as mentioned in python docs) by raising a `DispatcherFinalizing` exception
        * if ``:func listener_task:`` is then it is also cancelled


    Attributes:
        queue (asyncio.Queue): internal queue that is used to recieve events
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
        self.running = False
        self.listener_task = None
        if start_listening:
            self.listener_task = asyncio.create_task(self.listen_for_events())

    def __call__(self, *args, **kwargs):
        return self._queue.put_nowait((args, kwargs))

    async def listen_for_events(self):
        stop_flag = self.stop_flag
        que = self._queue
        self.running = True
        async with self.task_group:
            while True:
                try:
                    args, kwargs = await que.get()
                    if args == self._sentinel:
                        raise QueueShutDown()
                except QueueShutDown:
                    break

                if stop_flag():
                    break
                self.task_group.create_task(self.submit(*args, **kwargs))

    async def stop(self):
        async def bomb():
            raise DispatcherFinalizing('stop method is called for dispatcher')

        self.task_group.create_task(bomb())
        if sys.version_info >= (3, 13):
            self._queue.shutdown()
        else:
            await self._queue.put([self._sentinel] * 2)
        self.running = False
        if self.listener_task:
            self.listener_task.cancel()
            await asyncio.sleep(0)  # allowing all the things to happen before waiting on listener_task
            await self.listener_task


class AbstractHandler(ABC):

    @abstractmethod
    async def handle(self, event: NamedTuple):
        pass


class BaseHandler(AbstractHandler):
    __slots__ = ()

    def __call__(self, *args, **kwargs):
        return self.handle(*args, **kwargs)

    async def handle(self, event: NamedTuple):
        """called when event occurs"""


class RequestHandler(BaseHandler):
    __slots__ = ()

    async def handle(self, event: RequestEvent):
        pass


class AbstractDispatcher(ABC):

    @abstractmethod
    async def submit(self, event):
        pass

    @abstractmethod
    def register_handler(self, event_trigger, handler):
        pass


class BaseDispatcher(AbstractDispatcher):
    """
    Attributes:
        stop_flag (Callable[[None], bool]): gets called to check for exiting, should return bool
        transport (asyncio.BaseTransport): any transport object that is used to perform network i/o
        registry (dict): internal dictionary that get's looked up when an event occurs
    """
    __slots__ = ('transport', 'stop_flag', 'registry')

    def __init__(self, transport, stop_flag):
        self.transport = transport
        self.stop_flag = stop_flag
        self.registry = {}

    def __call__(self, *args, **kwargs):
        return self.submit(*args, **kwargs)

    async def submit(self, event):
        """Called when event occurs
        """

    def register_handler(self, event_trigger: enum.Enum | str | bytes,
                         handler: BaseHandler | AbstractDispatcher | Callable):
        """
        Args:
            handler(BaseHandler): this is called when registered event occurs
            event_trigger (str | bytes): event trigger to register with
        """
        self.registry[event_trigger] = handler


class RumorMessageList(ABC):
    @abstractmethod
    def sample_peers(self, message_id, sample_count):
        pass

    @abstractmethod
    def push(self, message: GossipMessage):
        pass


class RumorPolicy(ABC):
    @abstractmethod
    def __init__(self, protocol_class): ...

    @abstractmethod
    def should_rumor(self, message: GossipMessage): ...


__all__ = (
    'RumorMessageList',
    'RequestHandler',
    'AbstractHandler',
    'QueueMixIn',
    'AbstractDispatcher',
    'BaseHandler',
    'BaseDispatcher',
    'RumorPolicy',
)
