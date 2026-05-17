import asyncio
import logging
import socket
import sys
from asyncio import TaskGroup
from typing import Optional

from src.avails import RemotePeer, WireData, const, use
from src.avails.exceptions import InvalidPacket, RemotePeerNotFound
from src.avails.mixins import AExitStackMixIn, TaskGroupMixIn
from src.avails.useables import COLORS
from .connect import Socket
from .wire_io import WireIO

_logger = logging.getLogger(__name__)


class Acceptor(AExitStackMixIn):

    def __init__(
            self,
            finalizing: asyncio.Event,
            listen_addr: tuple,
            conn_service,
            peer_service,
            protocol,
            *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        from src.managers.connection import ConnectionManager
        self.address = listen_addr
        self._finalizing = finalizing
        self.conn_service: ConnectionManager = conn_service
        self.peer_service = peer_service
        self.main_socket: Optional[Socket] = None
        self.back_log = 4
        self.network_protocol = protocol
        self.blocked_ips = set()
        self._task_group = TaskGroup()

    async def initiate(self):
        _logger.info(f"Initiating Acceptor {self.address}")
        _logger.info("Listening for connections")
        self._start_socket()
        assert self.main_socket is not None

        stopping = self._finalizing.is_set
        while not stopping():
            try:
                initial_conn, addr = await self.main_socket.aaccept()
            except OSError:
                if stopping():
                    return
                raise

            if addr[0] in self.blocked_ips:
                initial_conn.close()
                _logger.info(f"connection from blocked ip, closing immediately: ip: {str(addr)}")
                continue

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
        if handshake is None:
            return
        _logger.info(f"handshake successful {handshake}")
        try:
            peer = await self.peer_service.get_remote_peer(handshake.peer_id)
        except RemotePeerNotFound:
            _logger.warning(f"RemotePeer with id={handshake.peer_id} not found in the network, closing an unexpected connection")
            initial_conn.close()
            return

        self.peer_service.change_peer_status(peer, RemotePeer.STATUS.ONLINE)
        self._exit_stack.enter_context(initial_conn)
        self.conn_service.new_connection(initial_conn, peer, handshake)

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
        return None

    def block_ip(self, ip):
        self.blocked_ips.add(ip)

    def unblock_ip(self, ip):
        self.blocked_ips.discard(ip)

    async def __aenter__(self):
        self._exit_stack.__aenter__()
        await self._exit_stack.enter_async_context(self._task_group)
        self._initiate_task = asyncio.create_task(self.initiate(), name="net.AcceptEndpoint")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await use.safe_cancel_task(self._initiate_task)
        return await super().__aexit__(exc_tb, exc_type, exc_tb)

    def __repr__(self):
        return f'<Acceptor({self.address})>'
