from src.core import *
import pickle
from typing import Tuple

from src.avails.constants import RP_FLAG  # control flag for this class
from itertools import count
# from ..avails.waiters import ThreadActuator
# import src.avails.connect as connect
_controller = ThreadActuator(None, control_flag=RP_FLAG)
TIMEOUT = 50  # sec


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
    __slots__ = 'username', 'uri', 'status', 'callbacks', 'req_uri', 'id', 'file_count'

    def __init__(self, username='admin', ip='localhost', port=8088, report=35896,
                 status=0):
        self.username = username
        self.uri = (ip, port)
        self.status = status
        self.callbacks = 0
        self.req_uri = (ip, report)
        self.id = f'{ip}{port}'
        self.file_count = count()

    def send_serialized(self, _to_send: connect.Socket):
        serialized = pickle.dumps(self)
        _to_send.send(struct.pack('!I', len(serialized)))
        _to_send.send(serialized)
        return True

    def __repr__(self):
        return f'RemotePeer({self.username}, {self.uri[0]}, {self.uri[1]}, {self.req_uri[1]}, {self.status})'

    def get_file_count(self):
        return next(self.file_count)

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

    def increment_file_count(self):
        self.file_count.__next__()

    @staticmethod
    def deserialize(to_recv: connect.Socket, actuator=_controller):

        reads, _, _ = select.select([to_recv, actuator], [], [], TIMEOUT)
        if to_recv not in reads or actuator.to_stop:
            return RemotePeer()
        try:
            raw_length = to_recv.recv(4)
            size_to_recv = struct.unpack('!I', raw_length)[0]

            reads, _, _ = select.select([to_recv, actuator], [], [],50)
            if to_recv not in reads or actuator.to_stop:
                return RemotePeer()

            serialized = to_recv.recv(size_to_recv)
            return pickle.loads(serialized)
        except Exception as e:
            print(f"::Exception while deserializing at remote_peer.py/avails: {e}")
            return RemotePeer(username="N/A", ip=to_recv.getpeername()[0], port=to_recv.getpeername()[1], )

    def __bool__(self):
        return bool(self.username or self.id or self.req_uri or self.uri)


def end():
    _controller()
    print("::RemotePeers Ended")

