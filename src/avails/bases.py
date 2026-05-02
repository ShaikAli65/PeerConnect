import enum
import sys
from abc import ABC, abstractmethod
from dataclasses import astuple, dataclass
from typing import Callable, ClassVar, Protocol

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


class AbstractDispatcher(ABC):

    @abstractmethod
    async def submit(self, event):
        pass

    @abstractmethod
    def register_handler(self, event_trigger, handler):
        pass


class Router:
    """Wrap a bunch of functions into a single callable object, calls respective handlers registered

    A Very lightweight dispatcher

    This provides a basic implementation, if any arguments are to be transformed or some other logic is to be applied
    subclasses can override `__call__` and implement their own logic
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = kwargs.pop('registry', {})

    def __call__(self, event_header, *args, **kwargs):
        return self.registry[event_header](*args, **kwargs)

    def register_handler(self, event_trigger, handler):
        self.registry[event_trigger] = handler


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
                         handler: AbstractDispatcher | Callable):
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
    registry: dict[str, type["AppEventBase"]] = {}

    def __new__(mcls, name, bases, namespace):
        cls = super().__new__(mcls, name, bases, namespace)

        if namespace.get("__register__", True):
            header = namespace.get("HEADER") or camel_to_snake(name)
            cls.HEADER = header
            mcls.registry[header] = cls
        return cls


@dataclass(frozen=True, slots=True)
class AppEventBase(metaclass=_EventMeta):
    """Application event base class.

    Every event has a header that is used to identify the event type.
    defaults to snake case of the class name, one can override this by setting HEADER class variable

    Always access the header via `AppEventBase.header` or `AppEventBase.event_name()` as
    per the context of the event
    """

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

    def __iter__(self):
        return astuple(self).__iter__()


__all__ = (
    'AbstractDispatcher',
    'BaseDispatcher',
    'HasIdProperty',
    'HasID',
    'HasPeerId',
    'AppEventBase',
    'Router',
)
