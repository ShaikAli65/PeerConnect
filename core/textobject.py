from core import *


class PeerText:
    """
            Encapsulates text operations for peer-to-peer file transfer.

            Allows sending and receiving text/strings over sockets, managing text information,
            handling potential conflicts with sending/recieving texts, and providing string-like
            behavior for iteration and size retrieval.
        """

    def __init__(self, text: str = '', sendsock: socket.socket = None):
        self.raw_text = text.encode(const.FORMAT)
        self.text_len_encoded = struct.pack('!I', len(self.raw_text))
        self.sock = sendsock

    def send(self) -> bool:
        self.sock.send(self.text_len_encoded)
        self.sock.sendall(self.raw_text)
        send_rawlength = self.sock.recv(4)
        send_length = struct.unpack('!I', send_rawlength)[0] if send_rawlength else 0
        if self.sock.recv(send_length) == const.TEXTSUCCESSHEADER:
            return True
        return False

    def receive(self) -> bool:
        recieve_rawlength = self.sock.recv(4)
        recieve_text_length = struct.unpack('!I', recieve_rawlength)[0] if recieve_rawlength else 0
        print(recieve_text_length)
        self.raw_text = self.sock.recv(recieve_text_length)
        if self.raw_text:
            self.sock.send(struct.pack('!I', len(const.TEXTSUCCESSHEADER)))
            self.sock.sendall(const.TEXTSUCCESSHEADER)
            return True
        return False

    def __str__(self):
        return self.raw_text.decode(const.FORMAT)

    def __repr__(self):
        return self.raw_text.decode(const.FORMAT)

    def __len__(self):
        return len(self.raw_text.decode(const.FORMAT))

    def __iter__(self):
        return iter(self.raw_text)