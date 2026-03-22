import asyncio
import logging
import socket
import sys
from asyncio import TaskGroup
from typing import Optional

from src.avails import RemotePeer, WireData, const, use
from src.avails.exceptions import InvalidPacket, RemotePeerNotFound
from src.avails.mixins import AExitStackMixIn
from src.net.events import ConnectionEvent
from . import bandwidth
from .connect import Connection, Socket
from .wire_io import WireIO
from src.avails.useables import COLORS

_logger = logging.getLogger(__name__)


class Acceptor(AExitStackMixIn):

    def __init__(
            self,
            finalizing: asyncio.Event,
            listen_addr:tuple,
            conn_service,
            peer_service,
            protocol,
            *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        from src.core.acceptor import ConnectionService
        self.address = listen_addr  # ip defaults to active ip
        self._finalizing = finalizing
        self.conn_service: ConnectionService = conn_service
        self.peer_service = peer_service
        self.main_socket: Optional[Socket] = None
        self.back_log = 4
        self.network_protocol = protocol
        self.max_timeout = 90
        self._task_group = TaskGroup()
        self._initiate_task = asyncio.create_task(self.initiate(), name="net.AcceptEndpoint")

    async def initiate(self):
        _logger.info(f"Initiating Acceptor {self.address}")
        _logger.info("Listening for connections")
        self._start_socket()
        await self._exit_stack.enter_async_context(self._task_group)
        stopping = self._finalizing.is_set
        while not stopping():
            try:
                initial_conn, addr = await self.main_socket.aaccept()
            except OSError:
                if stopping():
                    return
                raise

            self._task_group.create_task(
                self.__accept_connection(initial_conn),
                name=f"acceptor task for socket {addr=}"
            )
            _logger.info(f"new connection from {addr}")
            await asyncio.sleep(0)

    def _start_socket(self):
        try:
            sock = self.network_protocol.create_async_server_sock(
                asyncio.get_running_loop(),
                self.address,
                family=const.IP_VERSION,
                backlog=self.back_log
            )
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError:
            _logger.critical("failed to bind acceptor")
            print(COLORS.RED, const.BIND_FAILED_MSG, COLORS.RESET)
            return sys.exit(-1)

        self.main_socket = sock
        self._exit_stack.enter_context(sock)

    async def __accept_connection(self, initial_conn):

        handshake = await self._perform_handshake(initial_conn)
        if not handshake:
            return
        _logger.info(f"handshake successful {handshake}")
        try:
            peer = await self.peer_service.get_remote_peer(handshake.peer_id)
        except RemotePeerNotFound:
            _logger.warning("RemotePeer not found in the network, closing an unexpected connection")
            initial_conn.close()
            return

        peer.status = RemotePeer.ONLINE
        conn = Connection.create_from(initial_conn, peer)
        self._exit_stack.enter_context(initial_conn)
        con_event = ConnectionEvent(conn, handshake)
        watcher = bandwidth.Watcher()
        watcher.watch(initial_conn, conn)
        await self.conn_service.new_connection(con_event)

    @classmethod
    async def _perform_handshake(cls, initial_conn):
        try:
            raw_handshake = await asyncio.wait_for(
                WireIO.receive_async(initial_conn), const.SERVER_TIMEOUT
            )
            return WireData.load_from(raw_handshake)
        except TimeoutError:
            error_log = f"new connection inactive for {const.SERVER_TIMEOUT}s, closing"
        except OSError:
            error_log = f"Socket error"
        except InvalidPacket:
            error_log = f"Initial handshake packet is invalid, closing connection"

        if error_log := locals().get('error_log'):
            _logger.error(error_log)
            initial_conn.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await use.safe_cancel_task(self._initiate_task)
        return await super().__aexit__(exc_tb, exc_type, exc_tb)

    def __repr__(self):
        return f'Nomad{self.address}'
