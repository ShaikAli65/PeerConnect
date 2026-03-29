import enum
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, ClassVar, NamedTuple, Protocol

from src.avails.useables import camel_to_snake

if sys.version_info >= (3, 13):
    pass
else:
    class QueueShutDown(Exception):
        ...


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
        self.registry = kwargs.pop('registry', {})

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


class _EventMeta(type):
    registry: dict[str, type["EventBase"]] = {}

    def __new__(mcls, name, bases, namespace):
        cls = super().__new__(mcls, name, bases, namespace)

        if namespace.get("__register__", True):
            header = namespace.get("HEADER") or camel_to_snake(name)
            cls.HEADER = header
            mcls.registry[header] = cls


@dataclass(frozen=True, slots=True)
class AppEventBase(metaclass=_EventMeta):
    HEADER: ClassVar[str | None] = None

    @property
    def header(self) -> str:
        return type(self).event_name()

    @classmethod
    def event_name(cls) -> str:
        return cls.HEADER or camel_to_snake(cls.__name__)

    @classmethod
    def registered_headers(cls) -> tuple[str, ...]:
        return tuple(_EventMeta.registry)


__all__ = (
    'AbstractHandler',
    'AbstractDispatcher',
    'BaseHandler',
    'BaseDispatcher',
    'HasIdProperty',
    'HasID',
    'HasPeerId',
    'AppEventBase',
)
