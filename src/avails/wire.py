"""Every Wire Format of Peerconnect

Contains all the classes related to how data appears in wire transfer on top of ip protocols.

All classes provide serializing and de-serializing methods to make them ready to transfer over wire.

One special class of wire protocol ``:class RemotePeer:`` is available in ``:module avails/remotepeer:``

Any Class that wraps data is immutable, once created not modifications are allowed, create another

"""

import dataclasses
from dataclasses import dataclass
from typing import NamedTuple

import umsgpack

from src.avails import const as _const
from src.avails.exceptions import InvalidPacket

__all__ = (
    "WireData",
    "GossipMessage",
    "RumorMessageItem",
    "PalmTreeInformResponse",
    "PalmTreeSession",
    "OTMSession",
    "OTMInformResponse",
    "OTMChunk",
)


class WireData:
    _version = _const.VERSIONS["WIRE"]

    __slots__ = 'id', '_header', 'version', 'body', 'peer_id'

    def __init__(self, header=None, msg_id=None, peer_id=None, version=_version, **kwargs):
        self._header = header
        self.id = msg_id
        self.peer_id = peer_id
        self.version = version
        self.body = kwargs

    def __bytes__(self):
        list_of_attributes = [
            self._header,
            self.id,
            self.version,
            self.body,
            self.peer_id,
        ]
        return umsgpack.dumps(list_of_attributes)

    @classmethod
    def load_from(cls, data: bytes):
        list_of_attributes = None
        try:
            list_of_attributes = umsgpack.loads(data)
            header, _id, version, body, peer_id = list_of_attributes
        except (ValueError, umsgpack.UnpackException, TypeError) as exp:
            ip = InvalidPacket()
            ip.add_note(f"items count={list_of_attributes}")
            raise ip from exp

        return cls(header, _id, peer_id, version=version, **body)

    def match_header(self, data):
        return self._header == data

    def __getitem__(self, item):
        return self.body[item]

    def __setitem__(self, key, value):
        self.body[key] = value

    @property
    def header(self):
        return self._header

    @property
    def msg_id(self):
        return self.id

    @property
    def dict(self):  # for introspection or validation
        return {
            "header": self._header,
            "msg_id": self.id,
            "version": self.version,
            "peer_id": self.peer_id,
            **self.body,
        }

    def __str__(self):
        return f"<WireData(header={self._header}, id={self.id}, body={repr(self.body)[:30]})>"

    def __repr__(self):
        return str(self)


class GossipMessage:
    __slots__ = "actual_data"

    def __init__(self, message: WireData = None):
        self.actual_data = message or WireData()

    @property
    def message(self):
        return self.actual_data.body.get("message", None)

    @property
    def ttl(self):
        return self.actual_data.body.get("ttl", None)

    @property
    def created(self):
        return self.actual_data.body.get("created", None)

    @property
    def header(self):
        return self.actual_data.header

    @property
    def id(self):
        return self.actual_data.msg_id

    def fields_check(self):
        wire_data = self.actual_data
        match wire_data.dict:
            case {
                "id": _,
                "header": _,
                "created": _,
                "ttl": _,
            }:
                return True
            case _:
                return False

    def __bytes__(self):
        return bytes(self.actual_data)

    def __repr__(self):
        return f"<GossipMessage(id={self.id}, created={self.created}, ttl={self.ttl}, message={self.message[:11]},)>"


@dataclass(slots=True)
class RumorMessageItem:
    message_id: int
    time_in: float
    creation_time: float
    peer_list: set[str]

    def __next__(self):
        return self.peer_list.pop()

    def __eq__(self, other):
        return self.message_id == other.message_id

    def __hash__(self):
        return self.message_id

    def __lt__(self, other):
        return self.time_in < other.time_in

    @property
    def id(self):
        return self.message_id


@dataclass(slots=True)
class PalmTreeInformResponse:
    """
    Args:
        peer_id(str) : id of peer who created this response
        passive_addr(tuple[str, int]) : datagram endpoint address at where peer is reachable
        active_addr(tuple[str, int]) : stream endpoint address
        session_key(str) : echoing back the session_key received
    """

    peer_id: str
    passive_addr: tuple[str, int]
    active_addr: tuple[str, int]
    session_key: str

    def __bytes__(self):
        return umsgpack.dumps(dataclasses.astuple(self))  # noqa

    @staticmethod
    def load_from(data: bytes):
        peer_id, passive_addr, active_addr, session_key = umsgpack.loads(data)
        return PalmTreeInformResponse(
            peer_id, tuple(passive_addr), tuple(active_addr), session_key  # noqa
        )


@dataclass(slots=True)
class PalmTreeSession:
    """A dataclass that represents the structure of PalmTreeSession

    Args:
        originate_id (str) : the one who initiated this session
        adjacent_peers (list[str]) : all the peers to whom we should be in contact
        key (str) : session key used to encrypt data
        session_id (int) : self-explanatory
        fanout (int) : maximum number of resends this instance should perform for every packet received
        link_wait_timeout (double) : timeout for any i/o operations

    """

    originate_id: str
    adjacent_peers: list[str]
    session_id: int
    key: str
    fanout: int
    link_wait_timeout: int
    adjacent_peers: list[str]
    chunk_size: int


@dataclass(slots=True)
class OTMSession(PalmTreeSession):
    """
    Args:
        originate_id(str) : the one who initiated this session
        session_id(int) : self-explanatory
        key(str) : session key used to encrypt data
        fanout(int) : maximum number of resends this instance should perform for every packet received
        link_wait_timeout (double) : timeout for any i/o operations
        file_count(int) : number of files to be sent in this session
        adjacent_peers(list[str]) : all the peers to whom we should be in contact
        chunk_size(int) : size of chunk to read/write in the current session
    """

    file_count: int


class OTMInformResponse(PalmTreeInformResponse):
    __slots__ = ()
    __doc__ = PalmTreeInformResponse.__doc__


class OTMChunk(NamedTuple):
    chunk_number: int
    data: bytes

    # type: int

    def __bytes__(self):
        return umsgpack.dumps(self)

    @staticmethod
    def load_from(data: bytes):
        unpacked_data = umsgpack.loads(data)
        return OTMChunk(*unpacked_data)
