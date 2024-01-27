import random

from core import *
import pickle


class RemotePeer:
    def __init__(self, username: str = 'admin', ip: str = 'localhost', port: int = 8088, report:int = 35896, status: int = 0):
        self.username = username
        self.uri = (ip, port)
        self.status = status
        self.callbacks = 0
        self.req_uri = (ip, report)
        self.id = str()

    def serialize(self, _to_send: socket.socket) -> bool:
        if self.callbacks > const.MAX_CALL_BACKS:
            return False
        try:
            serialized = pickle.dumps(self)
            _to_send.send(struct.pack('!Q', len(serialized)))
            _to_send.send(serialized)
            return True
        except socket.error as e:
            print(f"::Exception while serializing retrying in 5sec: {e}")
            time.sleep(5)
            self.callbacks += 1
            return self.serialize(_to_send)

    def __repr__(self):
        return f'RemotePeer({self.username}, {self.uri[0]}, {self.uri[1]}, {self.status})'

    def __str__(self):
        return f'{self.username}~^~{self.uri[0]}~^~{self.uri[1]}'

    def __hash__(self) -> int:
        return hash(self.uri)

    def __eq__(self, obj) -> bool:
        if not isinstance(obj, RemotePeer):
            return NotImplemented
        return self.uri == obj.uri


def deserialize(torecv: socket.socket) -> RemotePeer:
    try:
        rawlength = torecv.recv(8)
        length = struct.unpack('!Q', rawlength)[0]
        serialized = torecv.recv(length)
        return pickle.loads(serialized)
    except Exception as e:
        print(f"::Exception while deserializing: {e}")
        return RemotePeer()
