from core import *


class PeerText:
    """
    Encapsulates text operations for peer-to-peer file transfer.

    Allows sending and receiving text/strings over sockets, managing text information,
    handling potential conflicts with sending/receiving texts, and providing string-like
    behavior for iteration and size retrieval.

    This Class Does Not Provide Any Error Handling Should Be Handled At Calling Functions.
    """

    def __init__(self, sendsock: socket.socket, text: str = ''):
        self.raw_text = text.encode(const.FORMAT)
        self.text_len_encoded = struct.pack('!I', len(self.raw_text))
        self.sock = sendsock

    def send(self) -> bool:
        """
        Send the stored text over the socket.

        Returns:
        - bool: True if the text was successfully sent; False otherwise.

        """
        self.sock.send(self.text_len_encoded)
        self.sock.sendall(self.raw_text)
        send_rawlength = self.sock.recv(4)
        send_length = struct.unpack('!I', send_rawlength)[0] if send_rawlength else 0
        if self.sock.recv(send_length) == const.TEXTSUCCESSHEADER:
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
        recieve_rawlength = self.sock.recv(4)
        recieve_text_length = struct.unpack('!I', recieve_rawlength)[0] if recieve_rawlength else 0
        self.raw_text = self.sock.recv(recieve_text_length) if recieve_text_length else b''
        if self.raw_text:
            self.sock.send(struct.pack('!I', len(const.TEXTSUCCESSHEADER)))
            self.sock.sendall(const.TEXTSUCCESSHEADER)
            if cmpstring:
                return True if self.raw_text == cmpstring.encode(const.FORMAT) else False
        return self.raw_text if self.raw_text else False

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
