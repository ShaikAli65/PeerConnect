from typing import NamedTuple, TYPE_CHECKING

from src.avails import GossipMessage, WireData


class RequestEvent(NamedTuple):
    root_code: bytes
    request: WireData
    from_addr: tuple[str, int]


class GossipEvent(NamedTuple):
    message: GossipMessage
    from_addr: tuple[str, int]


class ConnectionEvent(NamedTuple):
    if TYPE_CHECKING:
        from src.transfers.transports import StreamTransport
        transport: StreamTransport
    else:
        transport: None
    handshake: WireData


class StreamDataEvent(NamedTuple):
    data: WireData
    if TYPE_CHECKING:
        from src.transfers.transports import StreamTransport
        transport: StreamTransport
    else:
        transport: None
