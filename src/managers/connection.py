import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncContextManager

from src.avails import RemotePeer, Router, WireData, const
from src.avails.exceptions import InvalidPacket
from src.avails.mixins import AExitStackMixIn, TaskGroupMixIn
from src.avails.useables import Lock, get_unique_id, wrap_with_tryexcept
from src.managers.directorymanager import DirConnectionHandler
from src.managers.filemanager import BigFileConnectionHandler, FileConnectionHandler, OTMConnectionHandler
from src.net import ConnectionEvent, WireIO
from src.net.connection_pool import ConnectionPool
from src.net.requests import send_request
from src.transfers import HEADERS

_logger = logging.getLogger(__name__)

ConnectionContext = AsyncContextManager[ConnectionEvent]


async def init_connection_manager(req_service, exit_stack,current_profile, this_remote_peer):
    connection_router = Router()

    c_reg_handler = connection_router.register_handler
    c_reg_handler(HEADERS.CMD_FILE_CONN, FileConnectionHandler(current_profile))
    c_reg_handler(HEADERS.CMD_BIG_FILE_CONN, BigFileConnectionHandler(current_profile))
    c_reg_handler(HEADERS.CMD_DIR_CONN, DirConnectionHandler(current_profile))
    c_reg_handler(HEADERS.OTM_UPDATE_STREAM_LINK, OTMConnectionHandler())
    c_reg_handler(HEADERS.PING, PingHandler(this_remote_peer))

    connection_manager = ConnectionManager(connection_router, req_service)
    await exit_stack.enter_async_context(connection_manager)
    return connection_manager


class BandwidthWatcher:
    def __init__(
          self,
          connection_pool: ConnectionPool,
          max_combined_mbps=None,
    ):
        self.connection_pool = connection_pool
        self.max_combined_mbps = max_combined_mbps


class ConnectionManager(TaskGroupMixIn, AExitStackMixIn):
    def __init__(self, connection_router, req_service, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection_pool = ConnectionPool(
            const.MAX_TOTAL_CONNECTIONS,
            const.MAX_CONNECTIONS_BETWEEN_PEERS,
        )
        self.bandwith_limiter = BandwidthWatcher(self.connection_pool)
        self.connection_router = connection_router
        self._reachability_result_cache = {}
        self._connectivity_check_locks = defaultdict(Lock)
        self.req_service = req_service
        self._stopping = asyncio.Event()

    @asynccontextmanager
    async def get_connection(self, peer: RemotePeer):
        conn = self.connection_pool.get_free_connection(peer)

        try:
            if conn is not None:
                yield conn
            else:
                ...
        finally:
            if await self._is_connection_healthy(conn):
                self.connection_pool.mark_available(conn)
            else:
                self.connection_pool.remove(conn)

    async def _is_connection_healthy(self, connection):
        ...

    def new_connection(self, socket, peer: RemotePeer, handshake_data=None):
        connection = self.connection_pool.add(socket, peer)
        if handshake_data:
            con_event = ConnectionEvent(connection, handshake_data)
            self._route_connection(con_event)
        else:
            self._attach_listener(connection)

    def _route_connection(self, connection_event) -> asyncio.Task:

        @asynccontextmanager
        async def connection_event_ctx():
            try:
                yield connection_event
            finally:
                pass

        f = wrap_with_tryexcept(self.connection_router, connection_event_ctx, _logger=_logger)
        return self._task_group.create_task(f)

    async def is_peer_reachable(self, peer: RemotePeer):
        async def new_check():
            ping_data = WireData(
                header=HEADERS.REMOVAL_PING,
                msg_id=get_unique_id(str)
            )
            _logger.debug(f"connectivity check initiating for {peer}")
            try:
                t = send_request(self.req_service, ping_data, peer, expect_reply=True)
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

    def _prune(self, connection):
        self.connection_pool.remove(connection)

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
                        self._prune(connection)
                        break

                event = ConnectionEvent(connection, service_header)
                await self._route_connection(event)

        self._task_group.create_task(_listener())

    async def __aenter__(self):
        self._exit_stack.__aenter__()
        self._stopping.clear()
        await self._exit_stack.enter_async_context(self._task_group)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._stopping.set()
        return self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)


def PingHandler(this_peer):
    async def handler(event: ConnectionEvent):
        handshake = event.handshake
        echo = WireData(
            header=handshake.header,
            peer_id=this_peer.peer_id,
            msg_id=handshake.msg_id,
        )
        async with (conn := event.connection):
            await conn.send(bytes(echo))

    return handler
