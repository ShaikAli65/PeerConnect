import pickle
import struct
from itertools import count
from typing import Tuple

from . import connect, const


class RemotePeer:
    version = const.VERSIONS['RP']

    __annotations__ = {
        'username': str,
        'uri': Tuple[str, int],
        'status': int,
        'callbacks': int,
        'req_uri': Tuple[str, int],
        'id': str,
        'file_count': int
    }

    __slots__ = 'username', '_conn_port', 'status', 'callbacks', '_req_port', 'id', '_file_id', 'ip','_network_port'

    def __init__(self,
                 username='admin',
                 ip='localhost',
                 conn_port=8088,
                 req_port=8089,
                 net_port=8090,
                 status=0):
        self.username = username
        self.ip = str(ip)
        self._conn_port = conn_port
        self.status = status
        self.callbacks = 0
        self._req_port = req_port
        self._network_port = net_port
        self.id = f'{self.ip}{conn_port}'
        self._file_id = count()

    async def send_serialized(self, _to_send: connect.Socket):
        serialized = pickle.dumps(self)
        await _to_send.asendall(struct.pack('!f', self.version))
        await _to_send.asendall(struct.pack('!I', len(serialized)))
        await _to_send.asendall(serialized)
        return True

    @property
    def id_encoded(self) -> bytes:
        return self.id.encode(const.FORMAT)
    # def set_values(self, username, ip, port=None, report=None, status=None):
    #     self.username = username
    #     self.ip = ip
    #     self.

    def get_file_id(self):
        """
        gets a unique id (uses :func:itertools.count) to assign to a file sent to peer represented
        by this object
        """
        return next(self._file_id)

    def increment_file_count(self):
        return next(self._file_id)

    @classmethod
    async def deserialize(cls, sender_sock: connect.Socket):
        try:
            version = struct.unpack('!f', await sender_sock.arecv(4))[0]
            assert version == cls.version, 'versions not matching for remote peer'
            size_to_recv = struct.unpack('!I', await sender_sock.arecv(4))[0]
            serialized = await sender_sock.arecv(size_to_recv)

            return pickle.loads(serialized)
        except Exception as e:
            print(f"::Exception while deserializing at remote_peer.py/avails: {e}")
            return RemotePeer(username="N/A", ip=sender_sock.getpeername()[0], conn_port=sender_sock.getpeername()[1], )

    @property
    def uri(self):
        return self.ip, self._conn_port

    @property
    def req_uri(self):
        return self.ip, self._req_port

    @property
    def network_uri(self):
        return self.ip, self._network_port

    def __reduce__(self):
        return (
            self.__class__,
            (
                self.username,
                self.ip,
                self._conn_port,
                self._req_port,
                self._network_port,
                self.status
            ),
            {'id': self.id},
        )

    def __setstate__(self, state):
        for key, value in state.items():
            setattr(self, key, value)

    def __repr__(self):
        return f'RemotePeer({self.username}, {self.ip}, {self._conn_port}, {self._req_port}, {self._network_port}, {self.status})'

    def __bool__(self):
        return bool(self.username or self.id or self.req_uri or self.uri)

    def __str__(self):
        return (
            "---------------------------\n"
            f"Username: {self.username[0:18]}\n"
            f"ID      : {self.id}\n"
            "---------------------------\n"
        )

    def __hash__(self) -> int:
        return hash(self.uri)

    def __eq__(self, obj) -> bool:
        if not isinstance(obj, RemotePeer):
            return NotImplemented
        return self.uri == obj.uri and self.username == obj.username
