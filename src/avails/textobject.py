from collections import defaultdict

from src.core import *
from typing import Union
from src.avails.constants import PEER_TEXT_FLAG, DATA_WEAVER_FLAG
from src.managers.thread_manager import thread_handler, TEXT

p_controller = ThreadActuator(None, control_flag=PEER_TEXT_FLAG)
d_controller = ThreadActuator(None, control_flag=DATA_WEAVER_FLAG)
thread_handler.register_control(p_controller, which=TEXT)
thread_handler.register_control(d_controller, which=TEXT)
TIMEOUT = 4


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
        'sock': connect.Socket,
        'controller': ThreadActuator,
        'id': str,
    }
    __slots__ = 'raw_text', 'text_len_encoded', 'sock', 'id', 'chunk_size', 'controller',

    def __init__(self, refer_sock, text=b'', *, chunk_size=512, controller=p_controller):
        self.raw_text = text
        self.text_len_encoded = struct.pack('!I', len(self.raw_text))
        self.controller = controller
        self.sock = refer_sock
        self.chunk_size = chunk_size

    def send(self, *, require_confirmation=True) -> bool:
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
        self.sock.send(self.text_len_encoded)
        self.sock.sendall(self.raw_text)
        # if require_confirmation:
        #     return self.__recv_header()
        return True

    def receive(self, cmp_string: Union[str, bytes] = '', *, require_confirmation=True) -> Union[bool, bytes]:
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
        readable, _, _ = select.select([self.sock, self.controller], [], [], TIMEOUT)
        if self.controller.to_stop or self.sock not in readable:
            return b''

        text_length = struct.unpack('!I', self.sock.recv(4))[0]

        received_data = bytearray()
        try:
            self.sock.setblocking(False)
            safe_stop = self.controller
            recv = self.sock.recv
            while text_length > 0:
                if safe_stop.to_stop is True:
                    return b''
                try:
                    chunk = recv(min(self.chunk_size, text_length))
                except BlockingIOError:
                    continue
                if not chunk:
                    break
                text_length -= len(chunk)
                received_data.extend(chunk)
        finally:
            self.sock.setblocking(True)

        self.raw_text = bytes(received_data)

        if text_length > 0:
            self.sock.send(struct.pack('!I', 0))
            return b''
        # if require_confirmation:
        #    self.__send_header()

        if cmp_string:
            return self.raw_text == cmp_string

        return self.raw_text

    def compare(self, cmp_string: bytes):
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

        readable, _, _ = select.select([self.sock, self.controller], [], [], TIMEOUT)
        if self.controller.to_stop or self.sock not in readable:
            return False

        raw_length = self.sock.recv(4)
        if raw_length == b'':
            return False
        header_length = struct.unpack('!I', raw_length)[0]

        if self.controller.to_stop:
            return False
        if self.sock in readable:
            return self.sock.recv(header_length) == const.TEXT_SUCCESS_HEADER
        return False

    def __str__(self):
        """
        Get the string representation of the stored text.

        Returns:
        - str: The decoded string representation of the stored text.

        """
        return self.raw_text.decode(const.FORMAT)

    def __repr__(self):
        return (f"SimplePeerText(refer_sock='{self.sock.__repr__}',"
                f" text='{self.raw_text}',"
                f" chunk_size={self.chunk_size},"
                f" controller={self.controller})")

    def __len__(self):
        """
        Get the length of the stored text.

        Returns:
        - int: The length of the stored text.

        """
        return len(self.raw_text.decode(const.FORMAT))

    def __iter__(self):
        """
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
    """

    __annotations__ = {
        'data_lock': threading.Lock,
        '__data': dict
    }
    __slots__ = 'data_lock', '__data'

    def __init__(self, *, header: str = None, content: Union[str, dict, list, tuple] = None,
                 _id: Union[int, str, tuple] = None,
                 byte_data: str | bytes = None):
        self.data_lock = threading.Lock()
        if byte_data:
            self.__data: dict = json.loads(byte_data)
        else:
            self.__data: dict = defaultdict(str)
            self.__data['header'] = header
            self.__data['content'] = content
            self.__data['id'] = _id or const.THIS_OBJECT.id

    def dump(self):
        """
        Modifies data in json 's string format and,
        returns json string representation of the data
        :return str:
        """
        with self.data_lock:
            return json.dumps(self.__data)

    def match_content(self, _content) -> bool:
        with self.data_lock:
            return self.__data['content'] == _content

    def match_header(self, _header) -> bool:
        with self.data_lock:
            return self.__data['header'] == _header

    def send(self, receiver_sock, controller=d_controller):
        """
        Sends data as json string to the provided socket,
        This function is written on top of :class: `SimplePeerText`'s send function
        Args:
            :param controller: an optional controller to pass into SimplePeerText
            :param receiver_sock:

        Returns:
            :returns True if sends text successfully else False:
        """
        return SimplePeerText(receiver_sock, self.dump().encode(const.FORMAT), controller=controller).send()

    def receive(self, sender_sock, controller=d_controller):
        """
        Receives a text string from the specified sender socket and sets the values of the TextObject instance.
        Written on top of :class: `SimplePeerText`'s receive function

        :param sender_sock: The sender socket from which to receive the text string.
        :param controller: An optional controller to pass into SimplePeerText
        Returns:
            The updated TextObject instance
        """
        text_string = SimplePeerText(sender_sock, controller=controller)
        text_string.receive()
        self.__set_values(json.loads(str(text_string)))
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
                f"content : {str(self.content).strip(' \n')}\n"
                f"id      : {self.id}\n"
                f"--------------------------------------------------")

    def __repr__(self):
        return f'DataWeaver(content="{self.__data}")'


def stop_all_text():
    thread_handler.delete(d_controller)
    thread_handler.delete(p_controller)
    p_controller.signal_stopping()
    d_controller.signal_stopping()
    print("::All texts stopped")
