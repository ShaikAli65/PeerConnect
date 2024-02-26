from core import *


class PeerText:
    """
    Encapsulates text operations for peer-to-peer file transfer.

    Allows sending and receiving text/strings over sockets, managing text information,
    handling potential conflicts with sending/receiving texts, and providing string-like
    behavior for iteration and size retrieval.
    The text is encoded in UTF-8 format, and stored as bytes,
    all comparisons are done on the stored bytes.
    This Class Does Not Provide Any Error Handling Should Be Handled At Calling Functions.
    """

    def __init__(self, refer_sock: socket.socket, text: str = '', byteable=True):
        self.raw_text = text.encode(const.FORMAT) if byteable else text
        self.text_len_encoded = struct.pack('!I', len(self.raw_text))
        self.sock = refer_sock
        self.id = ''
        self.byte_able = byteable

    def send(self) -> bool:
        """
        Send the stored text over the socket.

        Returns:
        - bool: True if the text was successfully sent; False otherwise.

        """
        self.sock.sendall(self.text_len_encoded)
        self.sock.sendall(self.raw_text)
        send_raw_length = self.sock.recv(4)
        send_length = struct.unpack('!I', send_raw_length)[0] if send_raw_length else 0
        while True:
            readable, _, _ = select.select([self.sock], [], [], 0.001)
            if self.sock not in readable:
                continue
            if self.sock.recv(send_length) == const.TEXT_SUCCESS_HEADER:
                return True
        return False

    def receive(self, cmpstring='') -> [bool, bytes]:
        """
        Receive text over the socket.

        Parameters:
        - cmpstring (bytes): Optional comparison string for validation.

        Returns:
        - [bool, bytes]: If cmpstring is provided, returns True if received text matches cmpstring,
                        otherwise returns the received text as bytes.

        """
        receive_raw_length = self.sock.recv(4)
        receive_text_length = struct.unpack('!I', receive_raw_length)[0] if receive_raw_length else 0
        self.raw_text = self.sock.recv(receive_text_length)  # if receive_text_length else b''
        if self.raw_text:
            self.sock.send(struct.pack('!I', len(const.TEXT_SUCCESS_HEADER)))
            self.sock.sendall(const.TEXT_SUCCESS_HEADER)
            if cmpstring:
                return True if self.raw_text == (cmpstring.encode(const.FORMAT) if isinstance(cmpstring,str) else cmpstring) else False
        return self.raw_text if self.raw_text else False

    def decode(self):
        return self.raw_text.decode(const.FORMAT)

    def compare(self, cmp_string: bytes) -> bool:
        """
        Compare the stored text to a provided string.

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
