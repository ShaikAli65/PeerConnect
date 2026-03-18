"""
Closely coupled with core.connector
Works with accepting incoming connections
lazy loading is used to avoid circular import through initiate_acceptor function
"""

import asyncio
import logging
from asyncio import CancelledError
from collections import namedtuple

from src.avails import WireData, const
from src.avails.exceptions import InvalidPacket
from src.avails.mixins import BasicDispatcher
from src.core.app import AppType
from src.managers.directorymanager import DirConnectionHandler
from src.managers.filemanager import BigFileConnectionHandler, FileConnectionHandler, OTMConnectionHandler
from src.net import Acceptor, WireIO, bandwidth
from src.net.events import ConnectionEvent
from src.transfers import HEADERS

_logger = logging.getLogger(__name__)


async def initiate_acceptor(exit_stack, finalizing_event, addr_tuple_gen, current_profile, this_remote_peer):
    connection_dispatcher = ConnectionDispatcher()
    c_reg_handler = connection_dispatcher.register_handler
    c_reg_handler(HEADERS.CMD_FILE_CONN, FileConnectionHandler(current_profile))
    c_reg_handler(HEADERS.CMD_BIG_FILE_CONN, BigFileConnectionHandler(current_profile))
    c_reg_handler(HEADERS.CMD_DIR_CONN, DirConnectionHandler(current_profile))
    c_reg_handler(HEADERS.OTM_UPDATE_STREAM_LINK, OTMConnectionHandler())
    c_reg_handler(HEADERS.PING, PingHandler(this_remote_peer))

    acceptor = Acceptor(
        finalizing_event,
        addr_tuple_gen(ip=None, port=const.PORT_THIS),
        connection_dispatcher,
    )

    # warning, careful with order
    await exit_stack.enter_async_context(bandwidth.Watcher())
    await exit_stack.enter_async_context(connection_dispatcher)
    await exit_stack.enter_async_context(acceptor)
    return connection_dispatcher


class ConnectionDispatcher(*BasicDispatcher):
    """Dispatches incoming connections...

    ...Based on the handshake header, used to identify services registered for incoming connections

    Life Cycle of a Submitted ``ConnectionEvent``::

        [s1 dispatcher(con_event)] (QueueMixIn creates a task)
                |
        [s2 ConnectionDispatcher.submit] (connection event is sent to registered handler by spawning another task `see{1}`)
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

    Note:
        Closes connections if anything unexpected happens
    """
    __slots__ = ()
    _parking_lot = {}
    _parked_item = namedtuple("ConnectionAndWatcherTask", ("connection", "watcher_task"))

    def park(self, connection):
        async def watcher():
            conn_watcher = bandwidth.Watcher()
            connection.recv.resume()
            connection.send.resume()
            try:
                async with connection:
                    service_header = await asyncio.wait_for(WireIO.recv_msg(connection),
                                                            const.MAX_IDLE_TIME_FOR_CONN)
            except (TimeoutError, OSError, InvalidPacket):
                await conn_watcher.request_closing(connection)
                return
            else:
                event = ConnectionEvent(connection, service_header)
                self._parking_lot.pop(connection)  # remove from passive mode
                self(event)  # this spawns a separate Task with self.submit

        item = self._parked_item(
            connection,
            self._task_group.create_task(
                watcher(),
                name=f"watching socket for activity [> peer={connection.peer.ip}]"
            )
        )

        self._parking_lot[connection] = item

    async def submit(self, event: ConnectionEvent):
        _logger.info(f"dispatching connection with header {event.handshake.header}")
        try:
            return await self.call_handler(event.handshake.header, _logger, event)
        finally:
            await self._try_parking(event.connection)

    async def _try_parking(self, connection):

        def check_cancelling():
            our_task = asyncio.current_task()
            if our_task:
                return our_task.cancelling()
            else:
                return False

        conn_watcher = bandwidth.Watcher()
        if check_cancelling():
            await conn_watcher.request_closing(connection)
            return

        try:
            await asyncio.wait_for(connection.lock.acquire(), 1)
            connection.lock.release()
        except TimeoutError:
            _logger.error(f"failed to acquire connection lock, closing connection")
            await conn_watcher.request_closing(connection)
            # DECISION, whether we should forcefully release using
            # connection.lock.release() and park,
            # or to close connection itself
            return
        except CancelledError:
            if check_cancelling():
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
