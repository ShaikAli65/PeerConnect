import asyncio
import logging
import socket
import sys
import threading
import traceback
from asyncio import TaskGroup
from typing import Optional

from src.avails import WireData, const, use
from src.avails.exceptions import InvalidPacket
from src.avails.mixins import AExitStackMixIn, singleton_mixin
from src.core import peers
from src.core.app import ReadOnlyAppType
from src.core.events import ConnectionEvent
from . import bandwidth
from .connect import Connection, Socket
from .wire_io import WireIO
from ..avails.useables import COLORS

_logger = logging.getLogger(__name__)


@singleton_mixin
class Acceptor(AExitStackMixIn):
    __annotations__ = {
        'address': tuple,
        '__control_flag': threading.Event,
        'main_socket': Socket,
        'stopping': asyncio.Event,
    }

    def __init__(self, app_ctx: ReadOnlyAppType, listen_addr=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.address = listen_addr or app_ctx.addr_tuple(ip=None, port=const.PORT_THIS)  # ip defaults to active ip
        self._app_ctx = app_ctx
        self.main_socket: Optional[Socket] = None
        self.back_log = 4
        self.max_timeout = 90
        self._task_group = TaskGroup()
        self._initiate_task = asyncio.create_task(self.initiate())

    async def initiate(self):
        _logger.info(f"Initiating Acceptor {self.address}")
        _logger.info("Listening for connections")
        self._start_socket()
        await self._exit_stack.enter_async_context(self._task_group)
        stopping = self._app_ctx.finalizing.is_set
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
            sock = const.PROTOCOL.create_async_server_sock(
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
        peer = await peers.get_remote_peer(handshake.peer_id)
        conn = Connection.create_from(initial_conn, peer)
        self._exit_stack.enter_context(initial_conn)
        con_event = ConnectionEvent(conn, handshake)
        watcher = bandwidth.Watcher()
        watcher.watch(initial_conn, conn)
        self._app_ctx.connections.dispatcher(con_event)

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
        except Exception:
            print("*" * 79)
            traceback.print_exc()
            raise

        if error_log := locals().get('error_log'):
            _logger.error(error_log)
            initial_conn.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await use.safe_cancel_task(self._initiate_task)
        return await super().__aexit__(exc_tb, exc_type, exc_tb)

    def __repr__(self):
        return f'Nomad{self.address}'
