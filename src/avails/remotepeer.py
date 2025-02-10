import umsgpack

from src.avails import const


class RemotePeer:
    """Used to represent a peer details in network

    There are some attributes that are kept to keep this class compatible with kademlia package
    This Follows a structure that is required by kademila package's Node
    and added extra things used by code

    Note:
        * All the code that is used in peer-connect is meant to use
            1. ``:attr peer_id:`` to refer to peer object, (the conversions to ids are made at low level functions that work with kademlia)

            2. ``:attr uri:`` to work with (ip, port) that is used to connect with peer

            3. ``:attr req_uri:`` to work with (ip, port) that is used to contact with requests endpoint

        * If any attributes are added then they should be added to __iter__ method
    """

    ONLINE = 1
    OFFLINE = 0

    version = const.VERSIONS['RP']
    __annotations__ = {
        'username': str,
        'uri': tuple[str, int],
        'status': int,
        'callbacks': int,
        'req_uri': tuple[str, int],
        'id': bytes,
    }

    __slots__ = 'username', '_conn_port', 'status', '_req_port', 'id', 'ip', 'long_id', '_byte_cache'

    def __init__(self,
                 byte_id=b'\x00',
                 username=None,
                 ip=None,
                 conn_port=const.PORT_THIS,
                 req_port=const.PORT_REQ,
                 status=OFFLINE):
        self.username = username
        self.ip = str(ip)
        self._conn_port = conn_port
        self._req_port = req_port
        self.status = status
        self.id = byte_id
        self.long_id = int(byte_id.hex(), 16)
        self._byte_cache = None, None

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
            self.status,
        ])

    @property
    def uri(self):
        return const.THIS_IP.addr_tuple(port=self._conn_port, ip=self.ip)

    @property
    def req_uri(self):
        return const.THIS_IP.addr_tuple(port=self._req_port, ip=self.ip)

    @classmethod
    def load_from(cls, data: bytes):
        list_of_attrs = umsgpack.loads(data)
        return cls(*list_of_attrs)

    def is_relevant(self, match_string):
        """
        Used to qualify this remote peer object as a valid entity for a search string
        """
        return match_string in self.username

    def __bytes__(self):
        list_of_attributes = list(self)
        return umsgpack.dumps(list_of_attributes)

    @property
    def peer_id(self):
        return str(self.long_id)

    @property
    def serialized(self):
        hashed = hash(tuple(self))

        if hashed == self._byte_cache[0]:
            r = self._byte_cache[1]
        else:
            r = bytes(self)
            self._byte_cache = hashed, r

        return r

    def __repr__(self):
        return (
            f'RemotePeer('
            f'name={self.username},'
            f' ip={self.ip},'
            f' conn={self._conn_port},'
            f' req={self._req_port},'
            f' st={self.status})'
        )

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


def convert_peer_id_to_byte_id(peer_id: str):
    int_ed = int(peer_id)
    byt_ed = int_ed.to_bytes(16)
    return byt_ed
