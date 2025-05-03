from typing import NamedTuple

from src.avails.wire import GossipMessage, WireData
from src.net.connect import Connection, MsgConnection, NetAddr


class RequestEvent(NamedTuple):
    root_code: bytes
    request: WireData
    from_addr: NetAddr


class GossipEvent(NamedTuple):
    message: GossipMessage
    from_addr: NetAddr


class ConnectionEvent(NamedTuple):
    connection: Connection
    handshake: WireData


class MessageEvent(NamedTuple):
    msg: WireData
    connection: MsgConnection
