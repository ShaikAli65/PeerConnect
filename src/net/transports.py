import enum
import struct

from src.avails import WireData, use
from .connect import NetAddr

__all__ = 'RequestsTransport', 'KademliaTransport', 'DiscoveryTransport', 'GossipTransport', 'REQUESTS_FLAG'


class REQUESTS_FLAG(enum.IntFlag):
    NULL = 0
    KADEMLIA = 1
    DISCOVERY = 2
    GOSSIP = 4
    REQUEST = 8

    # extra header for non-standard requests, can be used for special cases
    # all the flags after this are for special cases
    EXTRA = 16
    ACK = 32  # special flag for ACK messages
    REQUIRE_ACK = 64  # special flag for messages that require ACK

    @property
    def max_byte_len(self):
        return 1

    @property
    def flag_to_bytes(self):
        return self.to_bytes(length=self.max_byte_len, byteorder='big', signed=False)

    @classmethod
    def bytes_to_flag(cls, data: bytes):
        return cls(int.from_bytes(data, byteorder='big', signed=False))


class RequestsTransport:
    """Wraps datagram to multiplex at Requests Endpoint

    Other services use to define service specific trigger header
    that gets added to the message when it is sent through Requests endpoint
    which is further used to detect and multiplex to different registered dispatchers

    Note:
        do not use this with **Wire.send_*(self.transport)**, that is for different purposes

    Usage:
        >>> class Subclass(RequestsTransport):
        >>>     routing_header = b'\x11'  # some code of one byte
    or:
        >>> RequestsTransport(transport, _event_trigger_header=b'\x23')  # noqa

    """

    __slots__ = 'transport', 'trigger'
    routing_header = REQUESTS_FLAG.REQUEST

    def __init__(self, transport, _event_trigger_header=None):
        super().__init__()
        self.transport = transport
        self.trigger = _event_trigger_header or self.routing_header

    def sendto(self, data: bytes, addr: NetAddr, *, extra=REQUESTS_FLAG.EXTRA):
        data_size = struct.pack('!I', len(req_data_in_bytes := bytes(data)))
        data_to_send = (self.trigger | extra).flag_to_bytes + data_size + req_data_in_bytes
        return self.transport.sendto(data_to_send, addr)

    def close(self):
        return self.transport.close()


class KademliaTransport(RequestsTransport):
    __slots__ = ()
    routing_header = REQUESTS_FLAG.KADEMLIA

    @use.override
    def sendto(self, data: bytes, addr: NetAddr, *, extra=REQUESTS_FLAG.EXTRA):
        formatted = bytes(WireData(data=data))
        return super().sendto(formatted, addr, extra=extra)


class DiscoveryTransport(RequestsTransport):
    __slots__ = ()
    routing_header = REQUESTS_FLAG.DISCOVERY


class GossipTransport(RequestsTransport):
    __slots__ = ()
    routing_header = REQUESTS_FLAG.GOSSIP
