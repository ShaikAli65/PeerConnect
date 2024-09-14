from itertools import count
from typing import Tuple

import umsgpack

from . import const


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

    __slots__ = 'username', '_conn_port', 'status', '_req_port', 'id', '_file_id', 'ip','_network_port', 'long_id'

    def __init__(self,
                 peer_id=b'\x00',
                 username=None,
                 ip=None,
                 conn_port=8088,
                 req_port=8089,
                 net_port=8090,
                 status=0):
        self.username = username
        self.ip = str(ip)
        self._conn_port = conn_port
        self.status = status
        self._req_port = req_port
        self._network_port = net_port
        self.id = peer_id
        self.long_id = int(peer_id.hex(), 16)
        self._file_id = count()

    def same_home_as(self, node):
        return self.ip == node.ip and self.req_uri == node.req_uri and self.uri == node.uri

    def distance_to(self, node):
        """
        Get the distance between this node and another.
        """
        return self.long_id ^ node.long_id

    def __iter__(self):
        """
        Enables use of RemotePeer as a tuple - i.e., tuple(node) works.
        """
        return iter([
            self.id,
            self.username,
            self.ip,
            self._conn_port,
            self._req_port,
            self._network_port,
            self.status,
        ])

    def get_file_id(self):
        """
        gets a unique id (uses :func:itertools.count) to assign to a file sent to peer represented
        by this object
        """
        return next(self._file_id)

    def increment_file_count(self):
        return next(self._file_id)

    @property
    def uri(self):
        return self.ip, self._conn_port

    @property
    def req_uri(self):
        return self.ip, self._req_port

    @property
    def network_uri(self):
        return self.ip, self._network_port

    @classmethod
    def load_from(cls, data: bytes):
        list_of_attrs = umsgpack.loads(data)
        return cls(*list_of_attrs)

    def is_relavent(self, match_string):
        """
        Used to qualify this remote peer object as a valid
        entity for a search string
        """
        if match_string in self.username:
            return True

    def __bytes__(self):
        list_of_attributes = list(self)
        # print("bytifying", list_of_attributes, "*"*50)  # debug
        return umsgpack.dumps(list_of_attributes)

    def __repr__(self):
        return f'RemotePeer({self.username}, {self.ip}, {self._conn_port}, {self._req_port}, {self._network_port}, {self.status})'

    def __bool__(self):
        return bool(self.username or self.id or self.req_uri or self.uri)

    def __str__(self):
        return repr(self)

    def __hash__(self) -> int:
        return hash(self.uri)

    def __eq__(self, obj) -> bool:
        if not isinstance(obj, RemotePeer):
            return NotImplemented
        return self.uri == obj.uri and self.username == obj.username

    def __lt__(self, obj) -> bool:
        if not isinstance(obj, RemotePeer):
            return NotImplemented
        return self.long_id < obj.long_id
