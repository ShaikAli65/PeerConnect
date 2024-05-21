import threading
from collections import defaultdict

from src.core import *
from typing import Union
from src.avails.constants import PEER_TEXT_FLAG


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
        'sock': socket.socket,
        '__control_flag': threading.Event,
        'id': str,
    }
    __slots__ = ('raw_text', 'text_len_encoded', 'sock', 'id', 'chunk_size', '__control_flag',)

    def __init__(self, refer_sock: socket.socket, text: str = '', byte_able=True, chunk_size=512, control_flag:threading.Event = None):
        self.raw_text = text.encode(const.FORMAT) if byte_able else text
        self.text_len_encoded = struct.pack('!I', len(self.raw_text))
        self.__control_flag = control_flag or PEER_TEXT_FLAG
        self.sock = refer_sock
        self.chunk_size = chunk_size

    def send(self) -> bool:
        """
        Send the stored text over the socket.
        Possible Errors:
        - ConnectionError: If the socket is not connected.
        - ConnectionResetError: If the connection is reset.
        - BrokenPipeError: If the connection is broken.
        - OSError: If an error occurs while sending the text.
        - struct.error: If an error occurs while packing the text length.
        Returns:
        - bool: True if the text was successfully sent; False otherwise.

        """
        self.sock.send(self.text_len_encoded)
        self.sock.sendall(self.raw_text)

        return self.__recv_header()

    def receive(self, cmp_string: Union[str, bytes] = '') -> Union[bool, bytes]:
        """
        Receive text over the socket.

        Parameters:
        - cmp_string [str, bytes]: Optional comparison string for validation.
        supports both string and byte string, resolves accordingly.

        Returns:
        - [bool, bytes]: If cmp_string is provided, returns True if received text matches cmp_string,
                        otherwise returns the received text as bytes.

        """

        while self.safe_stop:
            readable, _, _ = select.select([self.sock], [], [], 0.005)
            if self.sock in readable:
                raw_length = self.sock.recv(4)
                break
        else:
            return False if cmp_string else b''

        # buffer = bytearray()
        # self.sock.setblocking(False)
        # while self.safe_stop:
        #     data = self.sock.recv(4)
        #     buffer.extend(data)
        #     if len(buffer) == 4:
        #         break
        # raw_length = bytes(buffer)

        text_length_received = struct.unpack('!I', raw_length)[0] if raw_length else 0
        received_data = bytearray()

        while len(received_data) < text_length_received:

            while self.safe_stop:
                readable, _, _ = select.select([self.sock], [], [], 0.005)
                if self.sock in readable:
                    chunk = self.sock.recv(min(self.chunk_size, text_length_received - len(received_data)))
                    break
            else:
                return False if cmp_string else b''

            if not chunk:
                break
            received_data.extend(chunk)
        self.raw_text = bytes(received_data)

        if not self.raw_text:
            return b''

        self.__send_header()

        if cmp_string:
            return self.raw_text == (cmp_string.encode(const.FORMAT) if isinstance(cmp_string, str) else cmp_string)

        return self.raw_text

    def decode(self):
        return self.raw_text.decode(const.FORMAT)

    def compare(self, cmp_string: bytes) -> bool:
        """
        Compare the stored text to a provided string.
        accepts both byte string and normal string and checks accordingly.

        Parameters:
        - cmp_string (str): The string to compare to the stored text.

        Returns:
        - bool: True if the stored text matches cmp_string; False otherwise.

        """
        return self.raw_text == cmp_string

    def __send_header(self):
        self.sock.send(struct.pack('!I', len(const.TEXT_SUCCESS_HEADER)))
        self.sock.sendall(const.TEXT_SUCCESS_HEADER)

    def __recv_header(self):

        while self.safe_stop:
            readable, _, _ = select.select([self.sock, ], [], [], 0.005)
            if self.sock in readable:
                break
        else:
            return False

        header_raw_length = self.sock.recv(4)
        header_length = struct.unpack('!I', header_raw_length)[0] if header_raw_length else 0

        while self.safe_stop:
            readable, _, _ = select.select([self.sock, ], [], [], 0.005)
            if self.sock in readable:
                break
        else:
            return False
        return self.sock.recv(header_length) == const.TEXT_SUCCESS_HEADER

    @property
    def safe_stop(self):
        return self.__control_flag.is_set()

    def __str__(self):
        """
        Get the string representation of the stored text.

        Returns:
        - str: The decoded string representation of the stored text.

        """
        return self.raw_text.decode(const.FORMAT)

    def __repr__(self):
        return f"SimplePeerText(refer_sock='{self.sock}', text='{self.raw_text}', chunk_size={self.chunk_size})"

    def __len__(self):
        """
        Get the length of the stored text.

        Returns:
        - int: The length of the stored text.

        """
        return len(self.raw_text.decode(const.FORMAT))

    def __iter__(self):
        """
        Get an iterator for the stored text.

        Returns:
        - iter: An iterator for the stored text.

        """
        return self.raw_text.__iter__()

    def __eq__(self, other):
        return self.raw_text == other

    def __ne__(self, other):
        return self.raw_text != other

    def __hash__(self):
        return hash(self.raw_text)


class DataWeaver:
    """
    A wrapper class purposely designed to store data (as {header, content, id} format)
    provides send and receive functions
    Built on top of :class `SimplePeerText`:
    """

    __annotations__ = {
        'data_lock': threading.Lock,
        '__data': dict
    }
    __slots__ = ('data_lock', '__data')

    def __init__(self, *, header: str = None, content: Union[str, dict, list, tuple] = None, _id: Union[int, str, tuple] = None,
                 byte_data: bytes = None):
        self.data_lock = threading.Lock()
        if byte_data:
            self.__data: dict = json.loads(byte_data)
        else:
            self.__data: dict = defaultdict(str)
            self.__data['header'] = header
            self.__data['content'] = content
            self.__data['id'] = _id

    def dump(self) -> str:
        """
        Modifies data in json 's string format and,
        returns json string representation of the data
        :return str:
        """
        with self.data_lock:
            return json.dumps(self.__data)

    def match(self, _header: str = None, _content: str = None, _id: str = None) -> bool:
        with self.data_lock:
            if _header:
                return self.__data['header'] == _header
            elif _content:
                return self.__data['content'] == _content
            elif _id:
                return self.__data['id'] == _id

    def send(self, receiver_sock):
        """
        Sends data as json string to the provided socket,
        This function is written on top of SimplePeerText's send function

        :param receiver_sock:
        :returns True if sends text succesfully else False:
        """
        return SimplePeerText(text=self.dump(), refer_sock=receiver_sock).send()

    def receive(self, sender_sock):
        """
        Receives a text string from the specified sender socket and sets the values of the TextObject instance.
        Written on top of SimplePeerText's receive function
        Args:
            sender_sock: The sender socket from which to receive the text string.

        Returns:
            The updated TextObject instance.

        """
        text_string = SimplePeerText(refer_sock=sender_sock)
        text_string.receive()
        self.__set_values(json.loads(text_string.decode()))
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
        return self.__data.__str__()

    def __repr__(self):
        return f'DataWeaver(content="{self.__data}")'


def stop_all_text():
    PEER_TEXT_FLAG.clear()
