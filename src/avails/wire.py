import json as _json
import pickle
import struct
import threading as _threading
from collections import defaultdict
from typing import Union

from . import const as _const
from .connect import Socket as _Socket


class SendRecv:
    @staticmethod
    async def send_async(sock: _Socket, obj, serializer:pickle.dumps = None):
        data = serializer(obj)
        data_size = struct.pack('!I',len(data))
        await sock.asendall(data_size)
        await sock.asendall(data)

    @staticmethod
    def send(sock: _Socket, obj, serializer=pickle.dumps):
        data = serializer(obj)
        data_size = struct.pack('!I',len(data))
        sock.sendall(data_size)
        sock.sendall(data)

    @staticmethod
    async def receive_async(sock: _Socket, deserializer=pickle.loads):
        data_size = struct.unpack('!I', await sock.arecv(4))[0]
        data = await sock.arecv(data_size)
        return deserializer(data)

    @staticmethod
    def receive(sock: _Socket, deserializer=pickle.loads):
        data_size = struct.unpack('!I', sock.recv(4))[0]
        data = sock.recv(data_size)
        return deserializer(data)


class SimplePeerText:
    """
    Encapsulates text operations for peer-to-peer file transfer.
    Accepts A connected socket
    Allows sending and receiving text/strings over sockets, managing text information,
    handling potential conflicts with sending/receiving texts, and providing string-like
    behavior for iteration and size retrieval.
    The text is encoded in UTF-8 format(if not changed), and stored as bytes,
    all comparisons are done on the stored bytes.
    This Class Does Not Provide Any Error Handling Should Be Handled At Calling Functions.
    """

    __annotations__ = {
        'raw_text': bytes,
        'text_len_encoded': bytes,
        'sock': _Socket,
        'id': str,
    }
    __slots__ = 'raw_text', 'text_len_packed', '_sock', 'id', 'chunk_size', 'controller',

    def __init__(self, refer_sock: _Socket, data=b'', *, chunk_size=512):
        self.raw_text = data
        self.text_len_packed = struct.pack('!I', len(self.raw_text))
        self._sock = refer_sock
        self.chunk_size = chunk_size

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
        await self._sock.asendall(self.raw_text)
        if require_confirmation:
            return await self.__recv_cnf_header()
        return True

    async def receive(self, cmp_string: Union[str, bytes] = '', *, require_confirmation=False) -> Union[bool, bytes]:
        """
        Receive text over the socket.
        Better to check for `truthy` and `falsy` values for cmp_string as this function may return empty bytes.

        Parameters:
        - cmp_string [str, bytes]: Optional comparison string for validation.
        supports both string and byte string, resolves accordingly.

        Returns:
        - [bool, bytes]: If cmp_string is provided, returns True if received text matches cmp_string,
                        otherwise returns the received text as bytes.
        """
        text_length = struct.unpack('!I', await self._sock.arecv(4))[0]
        self.raw_text = await self._sock.arecv(text_length)
        if require_confirmation:
            await self.__send_cnf_header()
        if cmp_string:
            return self.raw_text == cmp_string
        return self.raw_text

    async def __send_cnf_header(self):
        await self._sock.asendall(_const.TEXT_SUCCESS_HEADER)

    async def __recv_cnf_header(self):
        data = self._sock.arecv(16)
        return data == _const.TEXT_SUCCESS_HEADER

    def __str__(self):
        """
        Get the string representation of the stored text.

        Returns:
        - str: The decoded string representation of the stored text.

        """
        return self.raw_text.decode(_const.FORMAT)

    def __repr__(self):
        return (f"SimplePeerText(refer_sock='{self._sock.__repr__()}',"
                f" text='{self.raw_text}',"
                f" chunk_size={self.chunk_size},"
                )

    def __len__(self):
        return len(self.raw_text.decode(_const.FORMAT))

    def __iter__(self):
        return self.raw_text.__iter__()

    def __eq__(self, other:bytes):
        return self.raw_text == other

    def __ne__(self, other):
        return self.raw_text != other

    def __hash__(self):
        return hash(self.raw_text)


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
        :return str:
        """
        with self.data_lock:
            return _json.dumps(self.__data)

    def match_content(self, _content) -> bool:
        return self.__data['content'] == _content

    def match_header(self, _header) -> bool:
        return self.__data['header'] == _header

    async def send(self, receiver_sock):
        """
        Sends data as _json string to the provided socket,
        This function is written on top of :class: `SimplePeerText`'s send function
        Args:
            :param receiver_sock:

        Returns:
            :returns True if sends text successfully else False:
        """
        return await SimplePeerText(receiver_sock, self.dump().encode(_const.FORMAT)).send()

    async def receive(self, sender_sock):
        """
        Receives a text string from the specified sender socket and sets the values of the TextObject instance.
        Written on top of :class: `SimplePeerText`'s receive function

        :param sender_sock: The sender socket from which to receive the text string.
        Returns:
            The updated TextObject instance
        """
        text_string = SimplePeerText(sender_sock)
        if await text_string.receive():
            self.__set_values(_json.loads(str(text_string)))
        return self

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
        return (f"--------------------------------------------------\n"
                f"header  : {self.header}\n"
                f"content : {self.content.strip(' \n')}\n"
                f"id      : {self.id}\n"
                f"--------------------------------------------------")

    def __repr__(self):
        return f'DataWeaver({self.__data})'


class WireData:
    version = _const.VERSIONS['WIRE']

    def __init__(self, _id, header, version=version, *args, **kwargs):
        self.id = _id
        self._header = header
        self.version = version
        self.body = kwargs
        self.ancillary_data = args

    def __bytes__(self):
        return pickle.dumps(self)

    async def send(self, sock):
        serial_data = bytes(self)
        payload_len = struct.pack('!I', len(serial_data))
        await sock.asendall(payload_len)
        await sock.asendall(serial_data)

    @staticmethod
    async def receive(sock:_Socket):
        payload_len = struct.unpack('!I', await sock.arecv(4))[0]
        data = await sock.arecv(payload_len)
        return pickle.loads(data)

    @staticmethod
    def load(data: bytes):
        return pickle.loads(data)

    def match_header(self, data):
        return self.header == data

    def __getitem__(self, item):
        return self.body[item]

    @property
    def header(self):
        return self._header
