from collections import defaultdict

from src.core import *
from typing import Union


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

    def __init__(self, refer_sock: socket.socket, text: str = '', byte_able=True, chunk_size=512):
        self.raw_text = text.encode(const.FORMAT) if byte_able else text
        self.text_len_encoded = struct.pack('!I', len(self.raw_text))
        self.sock = refer_sock
        self.id = ''
        self.chunk_size = chunk_size

    def send(self) -> bool:
        """
        Send the stored text over the socket.

        Returns:
        - bool: True if the text was successfully sent; False otherwise.

        """
        self.sock.send(self.text_len_encoded)
        self.sock.sendall(self.raw_text)
        send_raw_length = self.sock.recv(4)
        send_length = struct.unpack('!I', send_raw_length)[0] if send_raw_length else 0
        while True:
            readable, _, _ = select.select([self.sock], [], [], 0.001)
            if self.sock not in readable:
                continue
            if self.sock.recv(send_length) == const.TEXT_SUCCESS_HEADER:
                return True
            else:
                return False

    def receive(self, cmp_string='') -> Union[bool, bytes]:
        """
        Receive text over the socket.

        Parameters:
        - cmp_string (bytes): Optional comparison string for validation.

        Returns:
        - [bool, bytes]: If cmp_string is provided, returns True if received text matches cmp_string,
                        otherwise returns the received text as bytes.

        """
        receive_raw_length = self.sock.recv(4)
        receive_text_length = struct.unpack('!I', receive_raw_length)[0] if receive_raw_length else 0
        chunk_count = max(receive_text_length // self.chunk_size, 1)
        for i in range(chunk_count):
            self.raw_text += self.sock.recv(receive_text_length)  # if receive_text_length else b''
        if self.raw_text:
            self.sock.send(struct.pack('!I', len(const.TEXT_SUCCESS_HEADER)))
            self.sock.sendall(const.TEXT_SUCCESS_HEADER)
            if cmp_string:
                return True if self.raw_text == (
                    cmp_string.encode(const.FORMAT) if isinstance(cmp_string, str) else cmp_string) else False
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

    def __str__(self):
        """
        Get the string representation of the stored text.

        Returns:
        - str: The decoded string representation of the stored text.

        """
        return self.raw_text.decode(const.FORMAT)

    def __repr__(self):
        """
        Get the string representation of the stored text.

        Returns:
        - str: The decoded string representation of the stored text.

        """
        return self.raw_text.decode(const.FORMAT)

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
        return iter(self.raw_text)

    def __eq__(self, other):
        return self.raw_text == other

    def __ne__(self, other):
        return self.raw_text != other

    def __hash__(self):
        return hash(self.raw_text)


class DataWeaver:
    """
    A wrapper class purposely designed to store data as {header, content, id} format to use further
    provides send and receive functions

    """
    def __init__(self, header: str = None, content: str = None, _id: str = None, byte_data: bytes = None):
        self.data_lock = threading.Lock()
        if byte_data:
            self.__data: dict = json.loads(byte_data)
        else:
            self.__data: dict = defaultdict(str)
            self.__data['header'] = header
            self.__data['content'] = content
            self.__data['id'] = _id
        self.header = self.__data['header']
        self.content = self.__data['content']
        self.id = self.__data['id']

    def dump(self) -> str:
        """
        Modifies data in json 's string format and,
        returns json string representation of the data
        :return str:
        """
        with self.data_lock:
            return json.dumps(self.__data)

    def match(self,_header: str = None,_content: str = None,_id: str = None) -> bool:
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
        uses SimplePeerText's send function
        :param receiver_sock:
        :return:
        """
        return SimplePeerText(text=self.dump(),refer_sock=receiver_sock).send()

    def receive(self, sender_sock):
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

    def __str__(self):
        return self.__data.__str__()

    def __repr__(self):
        return f'DataWeaver({self.__data})'
