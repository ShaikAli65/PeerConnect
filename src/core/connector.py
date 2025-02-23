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
    active_conns: dict[
        RemotePeer,  # peer object
        set[connect.Connection],  # list of connections
    ] = defaultdict(set)

    passive_conns: dict[
        RemotePeer,  # peer object
        set[connect.Connection],  # list of connections
    ] = defaultdict(set)

    conn_waiters: dict[
        RemotePeer,
        asyncio.Condition,
    ] = defaultdict(asyncio.Condition)

    _global_conn_count = 0

    def _raise_resource_busy(self, peer):
        err = ResourceBusy()
        err.available_after = self.conn_waiters[peer]
        raise err

    @asynccontextmanager
    async def connect(self, peer,*, raise_if_busy=False):
        """Get a reliable connection to transfer data

        Callers should handle any slowdowns in throughput as bandwidth limiting is performed on need

        state machine::

            [s1 CHECK POOL]--(true)--> [s4 ret conn]
              |
           (false)
              |
            [s2 CHECK LIMIT]--(reached)-->[s3 wait (raise exp)] -> [s1]
              |
          (under limit)
              |
            [s3 CONNECT]--(success)--> [s4]
              |
          (failed)
              |
          [raise exp]

        Notes:
            Don't acquire lock of connection object returned, it's done internally
            and released on context manager exit

            Can be pruned or slowed down if resource limits are reached

        Args:
            peer (RemotePeer): to connect
            raise_if_busy(bool):
                if true then raises ResourceBusy which contains a condition that will be released,
                 signalling that to do something if needed

        Yields:
            connect.Connection : tuple that has sender/receiver pair, underlying socket, peer object

        Raises:
            CannotConnect: if peer is unreachable or a connection request is rejected
            ResourceBusy: if maximum number of concurrent connections are active and a new connection can't be made
        """

        watcher = bandwidth.Watcher()

        if passive_conns := self.passive_conns[peer]:
            active, closed = await watcher.refresh(peer, *passive_conns)
            self.passive_conns[peer].difference_update(set(closed))

            if active:
                one_connection = active.pop()
                del active  # drop the references early
                async with self._yield_connection_and_maintain(one_connection):
                    yield one_connection
                return

        if self.number_of_connections(peer) >= const.MAX_CONNECTIONS_BETWEEN_PEERS:
            if raise_if_busy is True:
                self._raise_resource_busy(peer)

            async with (condition := self.conn_waiters[peer]):
                await condition.wait()  # we get a signal if connections are freed

            async with self.connect(peer, raise_if_busy) as connection:
                yield connection

            return

        socket = await _create_conn(peer)
        connection = connect.Connection.create_from(socket, peer)
        watcher.watch(socket, connection)
        self._global_conn_count += 1

        async with self._yield_connection_and_maintain(connection):
            yield connection

    @asynccontextmanager
    async def _yield_connection_and_maintain(self, connection):
        """
        Some bookkeeping stuff with connection, and obtains lock on that connection until exited

        Args:
            connection(Connection): connection to look after
        Yields:
            connection
        """
        try:
            self.active_conns[connection.peer].add(connection)
            async with connection:
                yield connection
        finally:
            peer = connection.peer
            watcher = bandwidth.Watcher()
            active, _ = await watcher.refresh(peer, connection)
            if connection not in active:
                if connection in (conns := self.active_conns[peer]):
                    conns.remove(connection)
                    self._global_conn_count -= 1
            else:
                self.passive_conns[peer].add(connection)

            async with (signal := self.conn_waiters[peer]):
                signal.notify()
                # wake up something if waiting for connection getting freed

    def max_connections_that_can_be_made(self, peer: RemotePeer):
        return const.MAX_CONNECTIONS_BETWEEN_PEERS - len(self.active_conns.get(peer)) - len(
            self.passive_conns.get(peer)) - 1

    @property
    def conn_count(self):
        return self._global_conn_count

    def number_of_connections(self, peer):
        return len(self.active_conns.get(peer, set())) + len(self.passive_conns.get(peer, set()))
