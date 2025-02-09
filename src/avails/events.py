from typing import NamedTuple

from src.avails.connect import Connection
from src.avails.wire import GossipMessage, WireData


class RequestEvent(NamedTuple):
    root_code: bytes
    request: WireData
    from_addr: tuple[str, int]


class GossipEvent(NamedTuple):
    message: GossipMessage
    from_addr: tuple[str, int]


class ConnectionEvent(NamedTuple):
    connection: Connection
    handshake: WireData


class StreamDataEvent(NamedTuple):
    data: WireData
    connection: Connection
