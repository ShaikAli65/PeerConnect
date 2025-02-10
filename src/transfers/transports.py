import struct
from asyncio import BaseTransport
from typing import override

from src.avails import WireData
from src.transfers import REQUESTS_HEADERS


class RequestsTransport(BaseTransport):  # just for type hinting
    """Wraps datagram to multiplex at Requests Endpoint

    Other services use to define service specific trigger header
    that gets added to the message when it is sent through Requests endpoint
    which is further used to detect and multiplex to different registered dispatchers

    Note:
        no need to use this as **Wire.send_*(self.transport)**, that is only for bare sockets

    Usage:
        >>> class Subclass(RequestsTransport):
        >>>     _trigger = b'\x11'  # some code of one byte
    or:
        >>> RequestsTransport(transport, _event_trigger_header=b'\x23')  # noqa

    """

    __slots__ = 'transport', 'trigger'
    _trigger = b''

    def __init__(self, transport, _event_trigger_header=None):
        super().__init__()
        self.transport = transport
        self.trigger = self._trigger or _event_trigger_header

    def sendto(self, data: bytes, addr: tuple = None):
        data_size = struct.pack('!I', len(req_data_in_bytes := bytes(data)))
        data_to_send = self._trigger + data_size + req_data_in_bytes
        return self.transport.sendto(data_to_send, addr)

    def close(self):
        return self.transport.close()


class KademliaTransport(RequestsTransport):
    __slots__ = ()
    _trigger = REQUESTS_HEADERS.KADEMLIA

    @override
    def sendto(self, data: bytes, addr: tuple[str, int] | tuple[str, int, int, int] = None):
        formatted = bytes(WireData(data=data))
        return super().sendto(formatted, addr)


class DiscoveryTransport(RequestsTransport):
    __slots__ = ()
    _trigger = REQUESTS_HEADERS.DISCOVERY


class GossipTransport(RequestsTransport):
    __slots__ = ()
    _trigger = REQUESTS_HEADERS.GOSSIP
