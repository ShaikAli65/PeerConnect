from typing import NamedTuple

from src.avails.connect import Addr, Connection, MsgConnection
from src.avails.wire import GossipMessage, WireData


class RequestEvent(NamedTuple):
    root_code: bytes
    request: WireData
    from_addr: Addr


class GossipEvent(NamedTuple):
    message: GossipMessage
    from_addr: Addr


class ConnectionEvent(NamedTuple):
    connection: Connection
    handshake: WireData


class MessageEvent(NamedTuple):
    msg: WireData
    connection: MsgConnection
