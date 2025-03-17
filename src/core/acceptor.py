"""
Closely coupled with core.connector
Works with accepting incoming connections
lazy loading is used to avoid circular import through initiate_acceptor function
"""

import asyncio
import logging
import threading
import traceback
from asyncio import CancelledError, TaskGroup
from collections import namedtuple
from inspect import isawaitable
from typing import Optional

from src.avails import (BaseDispatcher, InvalidPacket, Wire, WireData, connect,
                        const, use)
from src.avails.connect import Connection
from src.avails.events import ConnectionEvent
from src.avails.mixins import AExitStackMixIn, QueueMixIn, singleton_mixin
from src.core import bandwidth, peers
from src.core.app import AppType, ReadOnlyAppType
from src.managers.directorymanager import DirConnectionHandler
from src.managers.filemanager import FileConnectionHandler, OTMConnectionHandler
from src.transfers import HEADERS

_logger = logging.getLogger(__name__)


def _task_name(handshake):
    return f"accept-con[{handshake.header}]"


async def initiate_acceptor(app_ctx: AppType):
    connection_dispatcher = ConnectionDispatcher()
    c_reg_handler = connection_dispatcher.register_handler
    c_reg_handler(HEADERS.CMD_FILE_CONN, FileConnectionHandler(app_ctx.read_only()))
    c_reg_handler(HEADERS.CMD_RECV_DIR, DirConnectionHandler(app_ctx.read_only()))
    c_reg_handler(HEADERS.OTM_UPDATE_STREAM_LINK, OTMConnectionHandler())
    c_reg_handler(HEADERS.PING, PingHandler(app_ctx.this_remote_peer))

    app_ctx.connections.dispatcher = connection_dispatcher

    acceptor = Acceptor(app_ctx.read_only())

    # warning, careful with order
    await app_ctx.exit_stack.enter_async_context(bandwidth.Watcher())
    await app_ctx.exit_stack.enter_async_context(connection_dispatcher)
    await app_ctx.exit_stack.enter_async_context(acceptor)


class ConnectionDispatcher(QueueMixIn, BaseDispatcher):
    """Dispatches incoming connections ...

    ... Based on the handshake header, used to identify services registered for incoming connections

    Life Cycle of a Submitted ``ConnectionEvent``::

        [s1 dispatcher(con_event)] (QueueMixIn creates a task)
                |
        [s2 ConnectionDispatcher.submit] (connection event is sent to registered handler by spawing another task `see{1}`)
                |
        [s3 handler returns]
                |
          [s4 Cancelled ?] -(false)-> [connection is parked] --(any activity)--> [s1]
                |                               |
             (true)                             ------(timeout)---> [s5]
                |
          [s5 Request for closure of `connection`]
                |
            (return)

    {1}: there is a chance of registered handler cancelling its task, which will lead to cancellation of submit task if submit
         directly awaits on handler, so we keep that in its own task

    """
    __slots__ = ()
    _parking_lot = {}
    _parked_item = namedtuple("ConnectionAndWatcherTask", ("connection", "watcher_task"))

    def park(self, connection):
        async def watcher():
            conn_watcher = bandwidth.Watcher()
            try:
                async with connection:
                    service_header = await asyncio.wait_for(Wire.recv_msg(connection), const.MAX_IDLE_TIME_FOR_CONN)
            except (TimeoutError, OSError):
                await conn_watcher.request_closing(connection)
            else:
                event = ConnectionEvent(connection, service_header)
                self._parking_lot.pop(connection)  # remove from passive mode
                self(event, _task_name=_task_name(event.handshake))  # this spawns a seperate Task with self.submit

        item = self._parked_item(
            connection,
            self._task_group.create_task(
                watcher(),
                name=f"watching socket for activity-[>{connection.socket.getpeername()}]"
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

        try:
            try:
                r = handler(event)
                if isawaitable(r):
                    await asyncio.ensure_future(r)
            except RuntimeError:
                await self._handle_runtime_error(_logger)
            except Exception as e:
                # we can't afford exceptions here as they move into QueueMixIn
                _logger.error(f"{handler}({event}) failed with \n", exc_info=e)

        finally:
            await self._try_parking(handler, event.connection)

    async def _try_parking(self, handler, connection):
        our_task = asyncio.current_task()
        cancelling = our_task.cancelling
        conn_watcher = bandwidth.Watcher()

        if cancelling():
            await conn_watcher.request_closing(connection)
            return

        try:
            await asyncio.wait_for(connection.lock.acquire(), 1)
            connection.lock.release()
        except TimeoutError:
            _logger.warning(f"failed to acquire connection lock from {handler}, closing connection")
            await conn_watcher.request_closing(connection)
            # DESICION, whether we should forcefully release
            # connection.lock.release() and park,
            # or to close connection itself
            return
        except CancelledError:
            if cancelling():
                await conn_watcher.request_closing(connection)
                return

        # park connection once the underlying lock is released
        self.park(connection)


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


@singleton_mixin
class Acceptor(AExitStackMixIn):
    __annotations__ = {
        'address': tuple,
        '__control_flag': threading.Event,
        'main_socket': connect.Socket,
        'stopping': asyncio.Event,
    }

    def __init__(self, app_ctx: ReadOnlyAppType, listen_addr=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.address = listen_addr or app_ctx.addr_tuple(ip=None, port=const.PORT_THIS)  # ip defaults to active ip
        self._app_ctx = app_ctx
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
        stopping = self._app_ctx.finalizing.is_set
        while not stopping():
            try:
                initial_conn, addr = await self.main_socket.aaccept()
            except OSError:
                if stopping():
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
        except OSError:
            print(const.BIND_FAILED)
            _logger.critical("failed to bind acceptor", exc_info=True)
            exit(-1)

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
        self._app_ctx.connections.dispatcher(con_event, _task_name=_task_name(handshake))

    @classmethod
    async def _perform_handshake(cls, initial_conn):
        try:
            raw_handshake = await asyncio.wait_for(
                Wire.receive_async(initial_conn), const.SERVER_TIMEOUT
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
