from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.avails import AppEventBase
from src.avails.wire import GossipMessage, WireData
from .connect import Connection, MsgConnection, NetAddr

__all__ = ('RequestEvent', 'GossipEvent', 'ConnectionEvent', 'MessageEvent')

if TYPE_CHECKING:
    from src.managers.connection import ConnectionManager


@dataclass(frozen=True, slots=True)
class NetworkEvent(AppEventBase):
    """Network Events Base Class"""


@dataclass(frozen=True, slots=True)
class RequestEvent(NetworkEvent):
    root_code: bytes
    request: WireData
    from_addr: NetAddr


@dataclass(frozen=True, slots=True)
class GossipEvent(NetworkEvent):
    message: GossipMessage
    from_addr: NetAddr


@dataclass(frozen=True, slots=True)
class ConnectionEvent(NetworkEvent):
    connection: Connection
    handshake: WireData


@dataclass(frozen=True, slots=True)
class MessageEvent(NetworkEvent):
    msg: WireData
    connection: MsgConnection
