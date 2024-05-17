from src.core import *
import pickle
from typing import Tuple

RP_FLAG = 3  # control flag for this class
control_flag = const.CONTROL_FLAG[RP_FLAG]


class RemotePeer:

    __annotations__ = {
        'username': str,
        'uri': Tuple[str, int],
        'status': int,
        'callbacks': int,
        'req_uri': Tuple[str, int],
        'id': str,
        'file_count': int
    }
    __slots__ = ['username', 'uri', 'status', 'callbacks', 'req_uri', 'id', 'file_count']

    def __init__(self, username: str = 'admin', ip: str = 'localhost', port: int = 8088, report: int = 35896,
                 status: int = 0):
        self.username = username
        self.uri = (ip, port)
        self.status = status
        self.callbacks = 0
        self.req_uri = (ip, report)
        self.id = ip
        self.file_count = 0

    def serialize(self, _to_send: socket.socket) -> bool:
        try:
            serialized = pickle.dumps(self)
            _to_send.send(struct.pack('!Q', len(serialized)))
            _to_send.send(serialized)
            return True
        except socket.error as e:
            print(f"::Exception while serializing... {e}")

    def __repr__(self):
        return f'RemotePeer({self.username}, {self.uri[0]}, {self.uri[1]}, {self.status})'

    def get_file_count(self):
        return self.file_count

    def __str__(self):
        return (
            "\n"
            "---------------------------\n"
            f"Username: {self.username[0:18]}\n"
            f"IP      : {self.id}\n"
            "---------------------------\n"
        )

    def __hash__(self) -> int:
        return hash(self.uri)

    def __eq__(self, obj) -> bool:
        if not isinstance(obj, RemotePeer):
            return NotImplemented
        return self.uri == obj.uri and self.username == obj.username

    def increment_file_count(self):
        self.file_count += 1


def deserialize(to_recv: socket.socket) -> RemotePeer:

    until_sock_is_readable(to_recv, control_flag=const.CONTROL_FLAG[RP_FLAG])

    try:
        raw_length = to_recv.recv(8)
        length = struct.unpack('!Q', raw_length)[0]
        serialized = to_recv.recv(length) if length else b''
        return pickle.loads(serialized)
    except Exception as e:
        print(f"::Exception while deserializing at remote_peer.py/avails: {e}")
        return RemotePeer(username="N/A",ip=to_recv.getpeername()[0], port=to_recv.getpeername()[1],)
