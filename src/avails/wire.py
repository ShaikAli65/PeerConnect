import json as _json
import struct
import threading as _threading
from asyncio import DatagramTransport
from collections import defaultdict
from typing import Union

import umsgpack

from . import Actuator, const as _const
from .connect import Socket as _Socket
from .useables import NotInUse, wait_for_sock_read

actuator = Actuator()


class Wire:
    @staticmethod
    async def send_async(sock: _Socket, data:bytes):
        data_size = struct.pack('!I',len(data))
        await sock.asendall(data_size)
        return await sock.asendall(data)

    @staticmethod
    def send(sock: _Socket, data:bytes):
        data_size = struct.pack('!I',len(data))
        return sock.sendall(data_size + data)

    @staticmethod
    def send_datagram(sock: _Socket | DatagramTransport, address, data: bytes):
        data_size = struct.pack('!I',len(data))
        return sock.sendto(data_size + data, address)

    @staticmethod
    async def receive_async(sock: _Socket):
        data_size = struct.unpack('!I', await sock.arecv(4))[0]
        data = await sock.arecv(data_size)
        return data

    @staticmethod
    def receive(sock: _Socket, timeout=None, controller=actuator):
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
        data, addr = sock.recvfrom(_const.MAX_DATAGRAM_SIZE)
        data_size = struct.unpack('!I', data[:4])[0]
        data = sock.recv(data[4: data_size + 4])
        return data, addr

    @staticmethod
    def load_datagram(data_payload):
        data_size = struct.unpack('!I', data_payload[:4])[0]
        return data_payload[4: data_size + 4]

    @staticmethod
    async def recv_datagram_async(sock: _Socket) -> tuple[bytes, tuple[str, int]]:
        data, addr = await sock.arecvfrom(_const.MAX_DATAGRAM_SIZE)
        data_size = struct.unpack('!I', data[:4])[0]
        data = data[4: data_size + 4]
        return data, addr


class DataWeaver:
    """
    A wrapper class purposely designed to store data (as {header, content, id} format)
    provides send and receive functions
    """

    __annotations__ = {
        'data_lock': _threading.Lock,
        '__data': dict
    }
    __slots__ = 'data_lock', '__data'

    def __init__(self, *, header: Union[str, int] = None, content: Union[str, dict, list, tuple] = None,
                 _id: Union[int, str, tuple] = None,
                 serial_data: str | bytes = None):
        self.data_lock = _threading.Lock()
        if serial_data:
            self.__data: dict = _json.loads(serial_data)
        else:
            self.__data: dict = defaultdict(str)
            self.__data['header'] = header
            self.__data['content'] = content
            self.__data['id'] = _id

    def dump(self):
        """
        Modifies data in _json 's string format and,
        returns _json string representation of the data
        :return: string
        """
        with self.data_lock:
            return _json.dumps(self.__data)

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
        with self.data_lock:
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

    def __str__(self):
        return "\n".join([f"{'-' * 50}",
                          f"header  : {self.header}",
                          f"content : {self.content}",
                          f"id      : {self.id}",
                          f"{'-' * 50}"])

    def __repr__(self):
        return f'DataWeaver({self.__data})'


class WireData:
    version = _const.VERSIONS['WIRE']

    def __init__(self, header=None, _id=None, *args, version=version, **kwargs):
        self.id = _id
        self._header = header
        self.version = version
        self.body = kwargs
        self.ancillary_data = args

    def __bytes__(self):
        list_of_attributes = [
            self._header,
            self.id,
            self.ancillary_data,
            self.version,
            self.body,
        ]
        return umsgpack.dumps(list_of_attributes)

    @classmethod
    def load_from(cls, data: bytes):
        list_of_attributes = umsgpack.loads(data)
        header, _id, *args, version, body = list_of_attributes
        return cls(header, _id, *args, version=version, **body)

    def match_header(self, data):
        return self._header == data

    def __getitem__(self, item):
        return self.body[item]

    @property
    def header(self):
        return self._header

    def __str__(self):
        return f"<WireData(header={self._header}, id={self.id}, body={self.body}, ancillary={self.ancillary_data})>"

    def __repr__(self):
        return str(self)


class GossipMessage:

    def __init__(self, message: WireData = WireData()):
        self.actual_data: WireData = message

    @staticmethod
    def wrap_gossip(data: WireData):
        return GossipMessage(data)

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
    
    def __bytes__(self):
        return bytes(self.actual_data)

    def __repr__(self):
        return f"<GossipMessage(id={self.id}, created={self.created}, ttl={self.ttl}, message={self.message[:11]},)>"


@NotInUse
class SimplePeerBytes:
    """
    Encapsulates byte operations for peer-to-peer file transfer.
    Accepts A connected socket
    Allows sending and receiving bytes over sockets, managing byte information,
    handling potential conflicts with sending/receiving texts, and providing string-like
    behavior for iteration and size retrieval.
    all comparisons are done on the stored bytes.
    This Class Does Not Provide Any Error Handling Should Be Handled At Calling Functions.
    """

    __annotations__ = {
        'raw_text': bytes,
        'text_len_encoded': bytes,
        'sock': _Socket,
        'id': str,
    }
    __slots__ = 'raw_bytes', 'text_len_packed', '_sock', 'id', 'chunk_size', 'controller',

    def __init__(self, refer_sock: _Socket, data=b'', *, chunk_size=512):
        self.raw_bytes = data
        self.text_len_packed = struct.pack('!I', len(self.raw_bytes))
        self._sock = refer_sock
        self.chunk_size = chunk_size
        self.controller = None  # used by synchronous send and receive to control loops and waiting operations

    async def send(self, *, require_confirmation=False) -> bool:
        """
        Send the stored text over the socket.
        Possible Errors:
        - ConnectionError: If the socket is not connected.
        - ConnectionResetError: If the connection is reset.
        - OSError: If an error occurs while sending the text.
        - struct.error: If an error occurs while packing the text length.
        Returns:
        - bool: True if the text was successfully sent; False otherwise.

        """
        await self._sock.asendall(self.text_len_packed)
        await self._sock.asendall(self.raw_bytes)
        if require_confirmation:
            return await self.__recv_cnf_header()
        return True

    async def receive(self, cmp_string: Union[str, bytes] = '', *, require_confirmation=False) -> Union[bool, bytes]:
        """
        Receive text over the socket asynchronously.
        Better to check for `truthy` and `falsy` values for cmp_string as this function may return empty bytes.

        Parameters:
        - cmp_string [str, bytes]: Optional comparison string for validation.
        supports both string and byte string, resolves accordingly.

        Returns:
        - [bool, bytes]: If cmp_string is provided, returns True if received text matches cmp_string,
                        otherwise returns the received text as bytes.
        """
        text_length = struct.unpack('!I', await self._sock.arecv(4))[0]
        self.raw_bytes = await self._sock.arecv(text_length)
        if require_confirmation:
            await self.__send_cnf_header()
        if cmp_string:
            return self.raw_bytes == cmp_string
        return self.raw_bytes

    async def __send_cnf_header(self):
        await self._sock.asendall(_const.TEXT_SUCCESS_HEADER)

    async def __recv_cnf_header(self):
        data = await self._sock.arecv(16)
        return data == _const.TEXT_SUCCESS_HEADER

    def send_sync(self, require_confirmation=False) -> bool:
        self._sock.send(self.text_len_packed)
        self._sock.sendall(self.raw_bytes)
        if require_confirmation:
            data = self._sock.recv(16)
            return data == _const.TEXT_SUCCESS_HEADER
        return True

    def receive_sync(self, cmp_string: Union[str, bytes] = '', *, controller=None, require_confirmation=False) -> Union[bool, bytes]:
        """
        Receive text over the socket synchronously.
        Better to check for `truthy` and `falsy` values for cmp_string as this function may return empty bytes.

        Parameters:
        - cmp_string [str, bytes]: Optional comparison string for validation.
        supports both string and byte string, resolves accordingly.

        Returns:
        - [bool, bytes]: If cmp_string is provided, returns True if received text matches cmp_string,
                        otherwise returns the received text as bytes.
        """
        text_length = struct.unpack('!I', self._sock.recv(4))[0]
        received_data = bytearray()
        b = self._sock.getblocking()
        self._sock.setblocking(False)
        self.controller = controller or Actuator()
        try:
            recv = self._sock.recv
            while text_length > 0:
                if self.controller.to_stop:
                    break
                try:
                    chunk = recv(min(self.chunk_size, text_length))
                    if not chunk:
                        break
                    text_length -= len(chunk)
                    received_data.extend(chunk)
                except BlockingIOError:
                    wait_for_sock_read(self._sock, self.controller, None)
        finally:
            self._sock.setblocking(b)

        if require_confirmation:
            self._sock.sendall(_const.TEXT_SUCCESS_HEADER)
        if cmp_string:
            return self.raw_bytes == cmp_string
        return self.raw_bytes

    def __str__(self):
        """
        Get the string representation of the stored text.

        Returns:
        - str: The decoded string representation of the stored text.

        """
        return self.raw_bytes.decode(_const.FORMAT)

    def __repr__(self):
        return (
            f"SimplePeerText(refer_sock='{self._sock.__repr__()}',"
            f" text='{self.raw_bytes}',"
            f" chunk_size={self.chunk_size},"
        )

    def __len__(self):
        return len(self.raw_bytes.decode(_const.FORMAT))

    def __iter__(self):
        return self.raw_bytes.__iter__()

    def __eq__(self, other:bytes):
        return self.raw_bytes == other

    def __ne__(self, other):
        return self.raw_bytes != other

    def __hash__(self):
        return hash(self.raw_bytes)


def unpack_datagram(data_payload):
    """ Unpack the datagram and handle exceptions """
    try:
        data = Wire.load_datagram(data_payload)
        return WireData.load_from(data)
    except umsgpack.UnpackException as ue:
        return print("Ill-formed data: %s. Error: %s" % (data_payload, ue))
    except TypeError as tp:
        return print("Type error, possibly ill-formed data: %s. Error: %s" % (data_payload, tp))
