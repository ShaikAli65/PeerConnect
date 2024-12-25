from abc import ABC, abstractmethod
from typing import NamedTuple

from src.avails import GossipMessage, Wire, WireData


# from src.core.transfers import REQUESTS_HEADERS  #  can't import here circular import


class RequestHandler(ABC):
    __slots__ = ()

    @abstractmethod
    def handle(self, event: NamedTuple):
        pass


class RumorMessageList(ABC):
    __slots__ = ()

    @abstractmethod
    def sample_peers(self, message_id, sample_count):
        pass

    @abstractmethod
    def push(self, message: GossipMessage):
        pass


class Dispatcher(ABC):
    __slots__ = ()

    @abstractmethod
    def dispatch(self, event: NamedTuple):
        pass

    def __call__(self, *args, **kwargs):
        return self.dispatch(*args, **kwargs)

    @abstractmethod
    def register_handler(self, event: NamedTuple, handler):
        pass


class RequestsTransport:
    """
        A class that other services use to define service specific trigger header
        that gets added to the message when it is sent through Requests endpoint
        which is further used to detect and multiplex to different registered dispatchers

    Usage:
        >>> class Subclass(RequestsTransport):
        >>>     trigger = 'custom header'
    """

    __slots__ = ('transport',)
    trigger = None

    def __init__(self, transport):
        self.transport = transport

    def sendto(self, data: bytes, addr: tuple[str, int] = None):
        # encapsulation
        req_data = WireData(
            header=self.trigger,
            data=data
        )
        return Wire.send_datagram(self.transport, addr, bytes(req_data))

    def close(self): ...


__all__ = (
    'RumorMessageList',
    'RequestHandler',
    'Dispatcher',
    'RequestsTransport',
)
