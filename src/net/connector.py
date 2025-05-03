"""
Closely coupled with core.acceptor
Works with connecting to other peer
"""
import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from src.avails import RemotePeer, const
from src.avails.exceptions import CannotConnect, ResourceBusy
from src.avails.mixins import AExitStackMixIn, singleton_mixin
from . import bandwidth
from .connect import Connection, connect_to_peer

_logger = logging.getLogger(__name__)

__all__ = (
    "Connector",
)


async def _create_conn(peer):
    """Connection helper for Connector.connect"""
    try:
        socket = await connect_to_peer(peer, timeout=1, retries=const.CONNECTION_RETRIES)
    except OSError as oe:
        raise CannotConnect from oe
    else:
        return socket


@singleton_mixin
class Connector(AExitStackMixIn):
    __slots__ = ()
    active_conns: dict[
        RemotePeer,  # peer object
        set[Connection],  # list of connections
    ] = defaultdict(set)

    passive_conns: dict[
        RemotePeer,  # peer object
        set[Connection],  # list of connections
    ] = defaultdict(set)

    conn_waiters: dict[
        RemotePeer,
        asyncio.Condition,
    ] = defaultdict(asyncio.Condition)

    _global_conn_count = 0

    def _raise_resource_busy(self, peer):
        err = ResourceBusy("resource busy")
        err.available_after = self.conn_waiters[peer]
        raise err

    @asynccontextmanager
    async def connect(self, peer, *, raise_if_busy=False, acquire_lock=True):
        """Get a reliable connection to transfer data

        Callers should handle any slowdowns in throughput as bandwidth limiting is performed on need

        Notes:
            * Can be pruned or slowed down if resource limits are reached

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

        Args:
            peer (RemotePeer): to connect
            raise_if_busy(bool):
                if true then raises ResourceBusy which contains a condition that will be released,
                 signalling that to do something if needed
            acquire_lock(bool):
                acquires internal lock of connection, this removes need for nested with statements,
                one for connect call and one for lock

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
                self.passive_conns[peer].remove(one_connection)
                del active  # drop the references early
                async with self._yield_connection_and_maintain(one_connection, acquire_lock):
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
        connection = Connection.create_from(socket, peer)
        watcher.watch(socket, connection)
        self._global_conn_count += 1

        async with self._yield_connection_and_maintain(connection, acquire_lock):
            yield connection

    @asynccontextmanager
    async def _yield_connection_and_maintain(self, connection, acquire_lock=True):
        """
        Some bookkeeping stuff with connection, and obtains lock on that connection
        if acquire lock is true, until exited

        Args:
            connection(Connection): connection to look after
            acquire_lock(bool):...
        Yields:
            connection
        """
        try:
            self.active_conns[connection.peer].add(connection)
            if acquire_lock:
                async with connection:
                    yield connection
            else:
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
                _logger.debug(f"added to passive list, {connection}")

            async with (signal := self.conn_waiters[peer]):  # condition returns none in its async context manager
                signal.notify_all()
                # wake up, if waiting for connection getting freed

    def max_connections_that_can_be_made(self, peer: RemotePeer):
        return const.MAX_CONNECTIONS_BETWEEN_PEERS \
            - len(self.active_conns.get(peer)) \
            - len(self.passive_conns.get(peer)) \
            - 1

    def is_connection_available(self, peer):
        return lambda: bool(self.passive_conns.get(peer, ()))

    @property
    def conn_count(self):
        return self._global_conn_count

    def number_of_connections(self, peer):
        return len(self.active_conns.get(peer, ())) + len(self.passive_conns.get(peer, ()))
