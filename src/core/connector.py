"""
Closely coupled with core.acceptor
Works with connecting to other peer
"""
import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from src.avails import RemotePeer, connect, const
from src.avails.exceptions import CannotConnect, ResourceBusy
from src.avails.mixins import AExitStackMixIn, singleton_mixin
from src.core import bandwidth

_logger = logging.getLogger(__name__)


async def _create_conn(peer):
    try:
        socket = await connect.connect_to_peer(peer, timeout=1, retries=const.CONNECTION_RETRIES)
    except OSError as oe:
        raise CannotConnect from oe
    else:
        return socket


@singleton_mixin
class Connector(AExitStackMixIn):
    __slots__ = ()
    connections: dict[
        RemotePeer,  # peer object
        set[connect.Connection],  # list of connections
    ] = defaultdict(set)

    conn_waiters: dict[
        RemotePeer,
        asyncio.Condition,
    ] = defaultdict(asyncio.Condition)

    _conn_count = 0

    def _raise_resource_busy(self, peer):
        err = ResourceBusy()
        err.available_after = self.conn_waiters[peer]
        raise err

    def _handle_error_for_conn(self, connection: connect.Connection, err):
        peer = connection.peer
        self.connections[peer].discard(connection)
        _logger.debug(f"error within connection {connection}", exc_info=True)
        self._conn_count -= 1

    @asynccontextmanager
    async def connect(self, peer, raise_if_busy=False):
        """Get a reliable connection to transfer data

        Callers should handle any slowdowns in throughput as bandwidth limiting is performed on need

        Notes:
            No need to acquire lock of connection object returned, it's done internally

            Can be pruned or slowed down if resource limits are reached

        Args:
            peer (RemotePeer): to connect
            raise_if_busy(bool):
                if true then raises ResourceBusy which contains a condition that will be released,
                 signalling that to do something if needed

        Yields:
            connect.Connection : tuple that has sender/receiver pair, underlying socket, peer object

        Raises:
            ResourceBusy: if maximum number of concurrent connections are active and a new connection can't be made

        """

        if len(self.connections.get(peer, ())) >= const.MAX_CONNECTIONS_BETWEEN_PEERS:
            if raise_if_busy is True:
                self._raise_resource_busy(peer)

            async with (signal := self.conn_waiters[peer]):
                await signal.wait()  # we get a signal if connections are freed

            if connection := self._get_connection(peer):
                async with self._yield_connection_and_maintain(connection):
                    yield connection
                return

        socket = await _create_conn(peer)
        connection = connect.Connection.create_from(socket, peer)
        watcher = bandwidth.Watcher()
        watcher.add_new_socket(socket, connection)
        self.connections[peer].add(connection)
        self._conn_count += 1

        async with self._yield_connection_and_maintain(connection):
            yield connection

    def _get_connection(self, peer):
        for conn in self.connections.get(peer):
            if conn.lock.locked():
                continue
            return conn

    @asynccontextmanager
    async def _yield_connection_and_maintain(self, connection, peer):

        try:
            async with connection:
                yield connection
        finally:
            watcher = bandwidth.Watcher()
            if await watcher.refresh(connection) is False:
                if connection in (conns := self.connections[peer]):
                    conns.remove(connection)
                    self._conn_count -= 1
            async with (signal := self.conn_waiters[peer]):
                signal.notify()
                # wake up something if waiting for connection

    def max_connections_that_can_be_made(self, peer: RemotePeer):
        return const.MAX_CONNECTIONS_BETWEEN_PEERS - len(self.connections.get(peer)) - 1

    @property
    def conn_count(self):
        return self._conn_count
