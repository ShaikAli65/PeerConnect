from collections import defaultdict

from src import net
from src.avails import RemotePeer


class ConnectionPool:
    """Maintains a pool of connections to peers.

    Also maintains different indexes for connection to retrieve based on the semantics.
    """

    def __init__(
          self,
          max_global_connections,
          max_per_peer,
          eviction_threshold=0.8,
    ):
        self.max_global = max_global_connections
        self.max_per_peer = max_per_peer
        self.eviction_threshold = int(max_global_connections * eviction_threshold)
        self._active_conns: dict[RemotePeer, set[net.Connection]] = defaultdict(set)
        self.connection_pool = defaultdict(set)
        self._socket_map = {}
        # Metrics
        self._total_connections = 0
        self._evictions = 0
        self._preemptions = 0

    def add(self, socket, peer):
        con = net.Connection.create_from(socket, peer)
        self.connection_pool[peer].add(con)
        self._socket_map[con] = socket
        return con

    def mark_available(self, connection):
        ...

    def remove(self, connection):
        """Removes connection from pool and returns socket associated with it."""
        self.connection_pool[connection.peer].remove(connection)
        return self._socket_map.pop(connection)

    def get_free_connection(self, peer) -> net.Connection:
        ...
