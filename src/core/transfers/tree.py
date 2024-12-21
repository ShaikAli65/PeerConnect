from abc import ABC, abstractmethod
from itertools import count

from src.avails.connect import Socket


class Tree(ABC):
    ...


class TreeLink(ABC):
    PASSIVE = 0x00
    ACTIVE = 0x01
    STALE = 0x02

    OFFLINE = 0x00
    ONLINE = 0x01
    LAGGING = 0x03

    OUTGOING = 0x01
    INCOMING = 0x02

    id_factory = count()

    def __init__(
            self, a: tuple, b: tuple, peer_id, connection=None, link_type: int = PASSIVE
    ):
        """
        Arguments:
            a = address of left end of this link
            b = address of right end of this link
            peer_id = id of peer on the other side
            connection (Socket) = a socket used to communicate between both ends
            link_type = ACTIVE (stream socket) or PASSIVE (datagram socket)
        """
        self.type = link_type
        self.peer_id = peer_id
        self.id = next(self.id_factory)

        # these are not exactly same as the one in that socket.getpeername and socket.getsockname
        self.left = a
        self.right = b
        self._connection: Socket = connection

        self.status = self.OFFLINE
        self.direction = self.OUTGOING

    @property
    def connection(self):
        return self._connection

    @connection.setter
    def connection(self, value):
        self.status = self.ONLINE
        self._connection = value

    @property
    def is_passive(self):
        return self.type == self.PASSIVE

    @property
    def is_active(self):
        return self.type == self.ACTIVE

    @property
    def is_online(self):
        return self.status == self.ONLINE

    @property
    def is_lagging(self):
        return self.status == self.LAGGING

    @property
    def is_outgoing(self):
        return self.direction == self.OUTGOING

    @abstractmethod
    def send_passive_message(self, message: bytes):
        ...

    @abstractmethod
    def send(self, data: bytes):
        ...

    @abstractmethod
    def recv(self, length: int):
        ...

    def __eq__(self, other):
        return other.id == self.id and self.right == other.right

    def __hash__(self):
        return hash(self.id) ^ hash(self.right) ^ hash(self.left)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        status = "offline"
        if self.is_lagging:
            status = "lagging"
        if self.is_online:
            status = "online"
        type_str = "active" if self.is_active else "passive"
        direction = "in" if self.direction == self.INCOMING else "out"
        return f"<{self.__class__.__name__}(id={self.id} l={self.left} r={self.right} {status} {type_str} {direction})>"

    def clear(self):
        self.status = self.OFFLINE
        try:
            if self._connection:
                self._connection.close()
        except OSError:
            pass  # Handle socket already closed
        self._connection = None
