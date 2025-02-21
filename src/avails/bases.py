import enum
import sys
from abc import ABC, abstractmethod
from typing import Callable, NamedTuple, Protocol

if sys.version_info >= (3, 13):
    pass
else:
    class QueueShutDown(Exception):
        ...

from src.avails.wire import GossipMessage
from src.avails.events import RequestEvent


class _HasID(Protocol):
    id: int | str  # Specify the type of the `id` attribute (e.g., int)


class HasPeerId(Protocol):
    peer_id: str


class HasIdProperty(Protocol):
    @property
    def id(self): ...


HasID = _HasID | HasIdProperty


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
        registry (dict): internal dictionary that gets looked up when an event occurs
    """

    __slots__ = 'registry',

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = {}

    def __call__(self, *args, **kwargs):
        return self.submit(*args, **kwargs)

    async def submit(self, event):
        """Called when event occurs
        """

    def register_handler(self, event_trigger: enum.Enum | str | bytes | int,
                         handler: BaseHandler | AbstractDispatcher | Callable):
        """
        Args:
            handler(BaseHandler): this is called when registered event occurs
            event_trigger (str | bytes): event trigger to register with
        """
        self.registry[event_trigger] = handler

    def get_handler(self, event_trigger):
        return self.registry.get(event_trigger, None)

    def remove_handler(self, event_trigger):
        return self.registry.pop(event_trigger)


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
    'AbstractDispatcher',
    'BaseHandler',
    'BaseDispatcher',
    'RumorPolicy',
    'HasIdProperty',
    'HasID',
    'HasPeerId'
)
