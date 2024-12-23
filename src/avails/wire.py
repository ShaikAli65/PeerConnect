"""Every Wire Format of Peerconnect

This module contains all the classes related to how data appears in wire transfer on top of ip protocols.

All classes provide serializing and de-serializing methods to make them ready to transfer over wire.

One special class of wire protocol :class: `RemotePeer` is available in :file: `remotepeer.py`

"""

import dataclasses
import json as _json
import struct
from asyncio import DatagramTransport
from collections import defaultdict
from dataclasses import dataclass
from typing import NamedTuple, Optional, Union

import umsgpack

from src.avails import Actuator, const as _const
from src.avails.connect import Socket as _Socket, is_socket_connected
from src.avails.useables import wait_for_sock_read

controller = Actuator()


class Wire:
    @staticmethod
    async def send_async(sock: _Socket, data: bytes):
        data_size = struct.pack('!I', len(data))
        return await sock.asendall(data_size + data)

    @staticmethod
    def send(sock: _Socket, data: bytes):
        data_size = struct.pack('!I', len(data))
        return sock.sendall(data_size + data)

    @staticmethod
    def send_datagram(sock: _Socket | DatagramTransport, address, data: bytes):
        if len(data) > _const.MAX_DATAGRAM_SEND_SIZE:
            raise ValueError(f"maximum send datagram size is {_const.MAX_DATAGRAM_SEND_SIZE} "
                             f"got a packet of size {len(data)} + 4bytes size")

        data_size = struct.pack('!I', len(data))
        return sock.sendto(data_size + data, address)

    @staticmethod
    async def receive_async(sock: _Socket):
        try:
            data_size = struct.unpack('!I', await sock.arecv(4))[0]
            data = await sock.arecv(data_size)
            return data
        except struct.error:
            if is_socket_connected(sock):
                raise
            else:
                raise OSError("connection broken")

    @staticmethod
    def receive(sock: _Socket, timeout=None, controller=controller):
        b = sock.getblocking()
        length_buf = bytearray()
        while len(length_buf) < 4:
            try:
                data = sock.recv(4 - len(length_buf))
                if data == b'':  # If socket connection is closed prematurely
                    sock.setblocking(b)
                    raise ConnectionError("got empty bytes in a stream socket")
                length_buf += data
            except BlockingIOError:
                wait_for_sock_read(sock, controller, timeout)
        data_length = struct.unpack('!I', length_buf)[0]

        received_data = bytearray()
        while len(received_data) < data_length:
            try:
                chunk = sock.recv(data_length - len(received_data))
                if chunk == b'':  # Again, handle premature disconnection
                    raise ConnectionError("connection closed during data reception")
                received_data += chunk
            except BlockingIOError:
                wait_for_sock_read(sock, controller, timeout)
        sock.setblocking(b)
        return received_data

    @staticmethod
    def recv_datagram(sock: _Socket):
        data, addr = sock.recvfrom(_const.MAX_DATAGRAM_RECV_SIZE)
        return Wire.load_datagram(data), addr

    @staticmethod
    def load_datagram(data_payload) -> bytes:
        data_size = struct.unpack('!I', data_payload[:4])[0]
        return data_payload[4: data_size + 4]

    @staticmethod
    async def recv_datagram_async(sock: _Socket) -> tuple[bytes, tuple[str, int]]:
        data, addr = await sock.arecvfrom(_const.MAX_DATAGRAM_RECV_SIZE)
        return Wire.load_datagram(data), addr


class WireData:
    _version = _const.VERSIONS['WIRE']

    __slots__ = 'id', '_header', 'version', 'body',

    def __init__(self, header=None, _id=None, version=_version, **kwargs):
        self._header = header
        self.id = _id
        self.version = version
        self.body = kwargs

    def __bytes__(self):
        list_of_attributes = [
            self._header,
            self.id,
            self.version,
            self.body,
        ]
        return umsgpack.dumps(list_of_attributes)

    @classmethod
    def load_from(cls, data: bytes):
        list_of_attributes = umsgpack.loads(data)
        header, _id, version, body = list_of_attributes
        return cls(header, _id, version=version, **body)

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
    def dict(self): # for introspection or validation
        return {'header':self._header, 'id':self.id,'version':self.version, **self.body}

    def __str__(self):
        return f"<WireData(header={self._header}, id={self.id}, body={self.body})>"

    def __repr__(self):
        return str(self)


def unpack_datagram(data_payload) -> Optional[WireData]:
    """
        Utility function to unpack data from :func: `datagram_received` callback from asyncio's DatagramProtocol
        or any other datagram transferred using wire protocol
        Unpack the raw data received using peer-connect's wire protocol
        into WireData and handle exceptions
    """
    try:
        data = Wire.load_datagram(data_payload)
        loaded = WireData.load_from(data)
        return loaded
    except umsgpack.UnpackException as ue:
        return print("Ill-formed data: %s. Error: %s" % (data_payload, ue))
    except TypeError as tp:
        return print("Type error, possibly ill-formed data: %s. Error: %s" % (data_payload, tp))
    except struct.error as se:
        return print("struct error, possibly ill-formed data: %s. Error: %s" % (data_payload, se))
    except Exception as e:
        return print("unexpected exception",e)


class DataWeaver:
    """
    A wrapper class purposely designed to store data (as {header, content, id} format)
    """

    __annotations__ = {
        '__data': dict,
    }
    __slots__ = '__data',

    def __init__(
            self,
            *,
            header: Union[str, int] = None,
            content: Union[str, dict, list, tuple] = None,
            _id: Union[int, str, tuple] = None,
            serial_data: str | bytes = None,
    ):
        if serial_data:
            self.__data: dict = _json.loads(serial_data)
        else:
            self.__data: dict = defaultdict(str)
            self.__data['header'] = header
            self.__data['content'] = content
            self.__data['id'] = _id

    def dump(self) -> str:
        """
        Modifies data in json string format and,
        returns json string representation of the data
        :return: string
        """
        return str(self)

    def match_content(self, _content) -> bool:
        return self.__data['content'] == _content

    def match_header(self, _header) -> bool:
        return self.__data['header'] == _header

    def __set_values(self, data_value: dict):
        self.__data = data_value
        self.header = self.__data['header']
        self.content = self.__data['content']
        self.id = self.__data['id']

    def __getitem__(self, key):
        return self.__data[key]

    def __setitem__(self, key, value):
        self.__data[key] = value

    @property
    def content(self):
        return self.__data['content']

    @content.setter
    def content(self, _content):
        self.__data['content'] = _content

    @property
    def header(self):
        return self.__data['header']

    @header.setter
    def header(self, _header):
        self.__data['header'] = _header

    @property
    def id(self):
        return self.__data['id']

    @id.setter
    def id(self, _id):
        self.__data['id'] = _id

    @property
    def type(self):
        return int.from_bytes(self.header[:1].encode())

    @property
    def is_reply(self):
        return self.header[0] == '\xff'

    def __str__(self):
        return _json.dumps(self.__data)

    def __repr__(self):
        return f'DataWeaver({self.__data})'


class StatusMessage:
    ...


class GossipMessage:
    __slots__ = 'actual_data'

    def __init__(self, message: WireData = None):
        self.actual_data = message or WireData()

    @property
    def message(self):
        return self.actual_data.body.get('message', None)

    @message.setter
    def message(self, data):
        self.actual_data.body['message'] = data

    @property
    def ttl(self):
        return self.actual_data.body.get('ttl', None)

    @ttl.setter
    def ttl(self, ttl):
        self.actual_data.body['ttl'] = ttl

    @property
    def created(self):
        return self.actual_data.body.get('created', None)

    @created.setter
    def created(self, value):
        self.actual_data.body['created'] = value

    @property
    def header(self):
        return self.actual_data.header

    @header.setter
    def header(self, value):
        self.actual_data._header = value

    @property
    def id(self):
        return self.actual_data.id

    @id.setter
    def id(self, value):
        self.actual_data.id = value

    def fields_check(self):
        wire_data = self.actual_data
        match wire_data.dict:
            case {
                'id':_,
                'header':_,
                'created':_,
                'ttl':_,
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


@dataclass(slots=True, frozen=True)
class PalmTreeInformResponse:
    """
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
        return PalmTreeInformResponse(peer_id, tuple(passive_addr), tuple(active_addr), session_key)


@dataclass(slots=True)
class PalmTreeSession:
    """
    Args:
        `originated_id(str)`: the one who initiated this session
        `adjacent_peers(list[str])` : all the peers to whom we should be in contact
        `session_key(str)` : session key used to encrypt data
        `session_id(int)` : self-explanatory
        `max_forwards`(int) : maximum number of resends this instance should perform for every packet received
        `link_wait_timeout`(double) : timeout for any i/o operations
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
        `originated_id(str)`: the one who initiated this session
        `session_id(int)` : self-explanatory
        `key(str)` : session key used to encrypt data
        `fanout`(int) : maximum number of resends this instance should perform for every packet received
        `link_wait_timeout`(double) : timeout for any i/o operations
        `file_count`(int) : number of files to be sent in this session
        `adjacent_peers(list[str])` : all the peers to whom we should be in contact
        `chunk_size(int)` : size of chunk to read/write in the current session
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
