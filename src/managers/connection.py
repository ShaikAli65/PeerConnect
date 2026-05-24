import asyncio
import logging
import time
from asyncio import TaskGroup
from collections import defaultdict
from contextlib import asynccontextmanager

from avails.exceptions import ConnectionNotFound
from src import net
from src.avails import RemotePeer, Router, WireData, const
from src.avails.exceptions import InvalidPacket
from src.avails.mixins import AExitStackMixIn
from src.avails.useables import Lock, get_unique_id, wrap_with_tryexcept
from src.controllers.bandwidth import BandwidthWatcher
from src.net import ConnectionEvent, WireIO
from src.net.connection_pool import ConnectionPool
from src.transfers import HEADERS

_logger = logging.getLogger(__name__)


async def init_connection_manager(req_service, this_peer,app_config, exit_stack):
    connection_manager = ConnectionManager(
        req_service,
        this_peer,
        app_config.protocol,
        const.CONNECTION_RETRIES
    )
    await exit_stack.enter_async_context(connection_manager)
    return connection_manager


class ConnectionManager(AExitStackMixIn):
    def __init__(self, req_service, this_peer, protocol, reconnect_retry_count, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection_pool = ConnectionPool(
            const.MAX_TOTAL_CONNECTIONS,
            const.MAX_CONNECTIONS_BETWEEN_PEERS,
        )
        self.bandwith_limiter = BandwidthWatcher(self.connection_pool)
        self.connection_router = Router()
        self.this_peer = this_peer
        self.network_protocol = protocol
        self.reconnect_retry_count = reconnect_retry_count
        self._reachability_result_cache = {}
        self._connectivity_check_locks = defaultdict(Lock)
        self.req_service = req_service
        self._stopping = asyncio.Event()
        self._task_group = TaskGroup()

    @asynccontextmanager
    async def get_connection(self, peer: RemotePeer):
        try:
            conn = self.connection_pool.get_free_connection(peer)
        except ConnectionNotFound:
            socket = await net.connect_to_peer(self.network_protocol, peer, retries=self.reconnect_retry_count)
            conn = self.connection_pool.add(socket, peer)

        try:
            yield conn
        finally:
            if await self._is_connection_healthy(conn):
                self.connection_pool.mark_available(conn)
            else:
                await self.close_connection(conn)

    async def new_connection(self, socket, peer: RemotePeer, handshake_data=None):
        connection = self.connection_pool.add(socket, peer)

        # This is a connection already used and re-entered, hence no handshake data is available
        if handshake_data is None:
            self._attach_listener(connection)
            return

        if not handshake_data.match_header(HEADERS.PING):
            con_event = ConnectionEvent(connection, handshake_data)
            self._route_connection(con_event)
            return

        un_ping = WireData(
            header=HEADERS.UNPING,
            peer_id=self.this_peer.peer_id,
            msg_id=handshake_data.msg_id,
        )
        await WireIO.send_msg(connection, un_ping)
        # Send a ping back to the peer to confirm that the connection is alive and keep
        # listening for incoming messages
        self._attach_listener(connection)

    async def is_peer_reachable(self, peer: RemotePeer):
        async def new_check():
            ping_data = WireData(
                header=HEADERS.REMOVAL_PING,
                msg_id=get_unique_id(str)
            )
            _logger.debug(f"connectivity check initiating for {peer}")
            try:
                t = self.req_service.send_request(ping_data, peer, expect_reply=True)
                await asyncio.wait_for(t, const.PING_TIMEOUT)
                return True
            except TimeoutError:
                # try a tcp connection if network is terrible with UDP

                # or another possibility that is observed:
                # windows does not forward packets to application level when system is locked or sleeping
                # (interfaces shutdown)
                pass

            try:
                async with self.get_connection(peer):
                    return True
            except ConnectionError:
                pass

            return False

        async with self._connectivity_check_locks[peer]:
            if peer in self._reachability_result_cache and \
                  time.monotonic() - self._reachability_result_cache[peer][1] \
                  < const.PING_TIME_CHECK_WINDOW:
                return self._reachability_result_cache[peer][0]
            else:
                what = await new_check()
                self._reachability_result_cache[peer] = (what, time.monotonic())
                return what

    async def close_connection(self, connection):
        socket = self.connection_pool.remove(connection)
        socket.close()

    @classmethod
    async def _is_connection_healthy(cls, connection):
        return net.is_socket_connected(connection.socket)

    def _route_connection(self, connection_event) -> asyncio.Task:

        @asynccontextmanager
        async def connection_event_ctx():
            try:
                yield connection_event
            finally:
                pass  # TODO: gather connection details for bookkeeping

        f = wrap_with_tryexcept(self.connection_router, connection_event_ctx, _logger=_logger)
        return self._task_group.create_task(f)

    def _attach_listener(self, connection):
        async def _listener():

            while not self._stopping.is_set():
                try:
                    service_header_func = asyncio.wait_for(
                        WireIO.recv_msg(connection),
                        const.MAX_IDLE_TIME_FOR_CONN
                    )
                    service_header = await service_header_func

                except (TimeoutError, OSError, InvalidPacket):
                    if await self._is_connection_healthy(connection):
                        continue
                    else:
                        await self.close_connection(connection)
                        break

                event = ConnectionEvent(connection, service_header)
                await self._route_connection(event)

        self._task_group.create_task(_listener(), name=f"connection-listener-{connection.peer_id}")

    async def __aenter__(self):
        await self._exit_stack.__aenter__()
        self._stopping.clear()
        await self._exit_stack.enter_async_context(self._task_group)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._stopping.set()
        return self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)

