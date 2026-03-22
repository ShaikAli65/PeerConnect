from typing import NamedTuple

from src.avails.wire import GossipMessage, WireData
from .connect import Connection, MsgConnection, NetAddr

__all__ = ('RequestEvent', 'GossipEvent', 'ConnectionEvent', 'MessageEvent')

NetworkEvent = NamedTuple


class RequestEvent(NetworkEvent):
    root_code: bytes
    request: WireData
    from_addr: NetAddr


class GossipEvent(NetworkEvent):
    message: GossipMessage
    from_addr: NetAddr


class ConnectionEvent(NetworkEvent):
    connection: Connection
    handshake: WireData


class MessageEvent(NetworkEvent):
    msg: WireData
    connection: MsgConnection
