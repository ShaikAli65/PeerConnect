"""
Closely coupled with core.connector
Works with accepting incoming connections
lazy loading is used to avoid circular import through initiate_acceptor function
"""

import asyncio
import logging
import threading
from asyncio import CancelledError, TaskGroup
from collections import namedtuple
from inspect import isawaitable
from typing import Optional

from src.avails import (BaseDispatcher, InvalidPacket, Wire, connect,
                        const)
from src.avails.connect import Connection
from src.avails.events import ConnectionEvent
from src.avails.mixins import AExitStackMixIn, QueueMixIn, singleton_mixin
from src.core import DISPATCHS, Dock, addr_tuple, bandwidth, connections_dispatcher, peers
from src.managers.directorymanager import DirConnectionHandler
from src.managers.filemanager import FileConnectionHandler, OTMConnectionHandler
from src.transfers import HEADERS

_logger = logging.getLogger(__name__)


async def initiate_acceptor():
    connection_dispatcher = ConnectionDispatcher()

    # data_dispatcher.register_handler(HEADERS.CMD_CLOSING_HEADER, ConnectionCloseHandler())

    c_reg_handler = connection_dispatcher.register_handler
    c_reg_handler(HEADERS.CMD_FILE_CONN, FileConnectionHandler())
    c_reg_handler(HEADERS.CMD_RECV_DIR, DirConnectionHandler())
    c_reg_handler(HEADERS.OTM_UPDATE_STREAM_LINK, OTMConnectionHandler())

    Dock.dispatchers[DISPATCHS.CONNECTIONS] = connection_dispatcher

    acceptor = Acceptor(finalizer=Dock.finalizing.is_set)

    # warning, careful with order
    await Dock.exit_stack.enter_async_context(connection_dispatcher)
    await Dock.exit_stack.enter_async_context(acceptor)


class ConnectionDispatcher(QueueMixIn, BaseDispatcher):
    __slots__ = ()
    _parking_lot = {}
    parked_item = namedtuple("ConnectionAndWatcherTask", ("connection", "watcher_task"))

    def park(self, connection):
        async def watcher():
            service_header = await Wire.recv_msg(connection)
            event = ConnectionEvent(connection, service_header)
            self._parking_lot.pop(connection)  # remove from passive mode
            await self.submit(event)

        item = self.parked_item(
            connection,
            asyncio.create_task(
                watcher(),
                name="watching socket for activity"
            )
        )

        self._parking_lot[connection] = item

    async def submit(self, event: ConnectionEvent):
        try:
            handler = self.registry[event.handshake.header]
        except KeyError:
            _logger.error(f"no handler found for event {event}")
            return

        _logger.info(f"dispatching connection with header {event.handshake.header} to {handler}")
        r = handler(event)

        if isawaitable(r):
            await r

        async with event.connection:
            # park connection once the underlying lock is released
            self.park(event.connection)


@singleton_mixin
class Acceptor(AExitStackMixIn):
    __annotations__ = {
        'address': tuple,
        '__control_flag': threading.Event,
        'main_socket': connect.Socket,
        'stopping': asyncio.Event,
    }

    def __init__(self, finalizer, listen_addr=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.address = listen_addr or addr_tuple(ip=None, port=const.PORT_THIS)  # ip defaults to active ip
        self.stopping = finalizer
        self.main_socket: Optional[connect.Socket] = None
        self.back_log = 4
        self.max_timeout = 90
        self._task_group = TaskGroup()
        self._initiate_task = asyncio.create_task(self.initiate())

    async def initiate(self):
        _logger.info(f"Initiating Acceptor {self.address}")
        _logger.info("Listening for connections")
        self._start_socket()
        await self._exit_stack.enter_async_context(self._task_group)
        while not self.stopping():
            try:
                initial_conn, addr = await self.main_socket.aaccept()
            except OSError:
                if self.stopping():
                    return
                raise
                # if we are finalizing then
                # it's mostly a case for asyncio cancelling this task

                # but,
                # async def accept_coro(future, conn):
                #   Coroutine closing the accept socket if the future is cancelled
                #   try:
                #       await future
                #   except exceptions.CancelledError:
                #       conn.close()
                #       raise
                #
                # this part of asyncio internals does not handle OSError,
                # causing a dirty log
                #
                # Task exception was never retrieved
                # future: < Task finished name = 'Task-6' coro = accept_coro() done,.. >
                # OSError: [WinError 995] The I/O operation has been aborted ...

                # try dealing with this

            self._task_group.create_task(
                self.__accept_connection(initial_conn),
                name=f"acceptor task for socket {addr=}"
            )
            _logger.info(f"New connection from {addr}")
            await asyncio.sleep(0)

    def _start_socket(self):
        sock = const.PROTOCOL.create_async_server_sock(
            asyncio.get_running_loop(),
            self.address,
            family=const.IP_VERSION,
            backlog=self.back_log
        )
        self.main_socket = sock
        self._exit_stack.enter_context(sock)

    async def __accept_connection(self, initial_conn):
        handshake = await self._perform_handshake(initial_conn)
        if not handshake:
            return
        peer = await peers.get_remote_peer_at_every_cost(handshake.peer_id)
        conn = Connection.create_from(initial_conn, peer)
        self._exit_stack.enter_context(initial_conn)
        con_event = ConnectionEvent(conn, handshake)
        watcher = bandwidth.Watcher()
        watcher.watch(initial_conn, conn)
        connection_disp = connections_dispatcher()
        connection_disp(con_event)

    @classmethod
    async def _perform_handshake(cls, initial_conn):
        error_log = ""
        try:
            hand_shake = await asyncio.wait_for(
                Wire.recv_msg(initial_conn), const.SERVER_TIMEOUT
            )
            return hand_shake
        except TimeoutError:
            error_log = f"new connection inactive for {const.SERVER_TIMEOUT}s, closing"
        except OSError:
            error_log = f"Socket error"
        except InvalidPacket:
            error_log = f"Initial handshake packet is invalid, closing connection"

        if error_log:
            _logger.error(error_log)
            initial_conn.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._initiate_task.cancel(sentinel := object())

        try:
            await self._initiate_task
        except CancelledError as ce:
            if ce.args and ce.args[0] is sentinel:
                pass
            else:
                raise

        return await super().__aexit__(exc_tb, exc_type, exc_tb)

    def __repr__(self):
        return f'Nomad{self.address}'
