"""Messages dispatchers and senders

Working:

* MsgDispatcher
    - CMD_TEXT : MessageHandler

* ConnectionsDispatcher
    - CMD_MSG_CONN: MessageConnHandler
    - PING: PingHandler

* MessageConnHandler
    Reads stream, creates message events, calls message dispatcher to dispatch message events

"""
import asyncio
import logging
from contextlib import AsyncExitStack
from functools import partial
from typing import NamedTuple

from src.avails import RemotePeer, WireData, const, use
from src.avails.exceptions import CannotConnect, InvalidPacket, RemotePeerNotFound
from src.avails.mixins import Dispatcher
from src.conduit import webpage
from src.core.acceptor import ConnectionService
from src.net import Connection, MsgConnection, MsgConnectionNoRecv, WireIO, bandwidth
from src.net.connector import Connector
from src.net.events import ConnectionEvent, MessageEvent
from src.transfers import HEADERS
from src.transfers.messages import MsgReceiver, MsgSender

_logger = logging.getLogger(__name__)
_exit_stack = AsyncExitStack()


async def initiate(app_runtime, this_peer, conn_service: ConnectionService):
    data_dispatcher = MsgDispatcher()
    data_dispatcher.register_handler(HEADERS.CMD_TEXT, MessageHandler())
    msg_conn_handler = MessageConnHandler(app_runtime.finalizing, data_dispatcher, this_peer)
    conn_service.dispatcher.register_handler(HEADERS.CMD_MSG_CONN, msg_conn_handler)
    conn_service.dispatcher.register_handler(HEADERS.PING, PingHandler(this_peer))
    conn_service.dispatcher.register_handler(
        HEADERS.CMD_MSG_CONN_RECV_LOOP_BACK,
        MessageRecvLoopBackHandler(app_runtime.finalizing, data_dispatcher)
    )
    await app_runtime.exit_stack.enter_async_context(data_dispatcher)
    await app_runtime.exit_stack.enter_async_context(_exit_stack)
    await _exit_stack.enter_async_context(_msg_conn_pool)
    return MsgConnService(data_dispatcher, this_peer)


class MsgDispatcher(*Dispatcher):
    __slots__ = ()

    async def submit(self, event: MessageEvent):

        # self.reply_arrived(event.msg)  # no need of this
        # handled directly at recv loop as an optimization
        h = self.call_handler(event.msg.header, _logger, event)
        try:
            return await asyncio.wait_for(h, const.TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK)
        except TimeoutError:
            return _logger.debug(f"timeout at message processing task, cancelling {event} task")


class MsgConnService(NamedTuple):
    dispatcher: MsgDispatcher
    this_peer: RemotePeer


# ================
# connection pool
# ================

class _MsgConnectionPool:
    _internal_msg_conn_pool = {}  # type: dict[str, MsgConnectionNoRecv]
    # k:v :: peer_id: message-connection

    _connector_calls = {}

    def add(self, connection: Connection):
        """Adds connection to pool

        Gets peer_id from connection

        Creates a msg connection that has no recv method and adds that, returns it

        Args:
            connection(Connection): connection to pool
        Returns:
            MsgConnectionNoRecv: msg connection into a send-only one
        """

        msg_conn_no_recv = self._internal_msg_conn_pool[connection.peer.peer_id] = MsgConnectionNoRecv(
            connection)
        return msg_conn_no_recv

    def get(self, peer_id):
        return self._internal_msg_conn_pool.get(peer_id, None)

    def remove(self, peer_id):
        return self._internal_msg_conn_pool.pop(peer_id, None)

    async def enter_connector(self, connector_callback):
        connection = await connector_callback.__aenter__()
        self._connector_calls[connection] = connector_callback
        return connection

    async def exit_connector_context(self, connection: Connection):
        if connection not in self._connector_calls:
            return None

        connector_lock = self._connector_calls.pop(connection)
        return await connector_lock.__aexit__(*[None] * 3)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        nones = [None] * 3
        for conn, _exit in self._connector_calls.items():
            try:
                await _exit.__aexit__(*nones)
            except Exception as exp:
                _logger.warning(
                    "not expecting error in exiting connection context of message connection: {conn}",
                    exc_info=exp,
                )


_msg_conn_pool = _MsgConnectionPool()


async def _get_from_pool(peer):
    """Get connection from pool
    Checks whether any connection is available in pool or not

    If a connection is found in pool,
        then checks if the connection is active or not
        if not removes connection from pool

    Returns:
        None | MsgConnectionNoRecv : None if connection is not found or inactive else corresponding MsgConnection object
    """

    connection = _msg_conn_pool.get(peer.peer_id)
    if connection is None:
        return connection

    closed = await _refresh_pool(peer, connection)
    if closed:
        return None

    return connection


async def _refresh_pool(peer, msg_connection):
    """Refresh connection pool by checking whether the connection is still active or not

    Args:
        peer(RemotePeer)
        msg_connection(MsgConnection)

    Returns:
        bool: indicating whether the connection is removed or not
    """
    watcher = bandwidth.Watcher()
    closed = await watcher.close_if_not_active(peer, msg_connection.connection)
    if closed:
        _msg_conn_pool.remove(peer.peer_id)
        await _msg_conn_pool.exit_connector_context(msg_connection.connection)
        return closed

    return False


# =============
# handlers
# =============


def MessageHandler():
    """Handle an incoming message"""

    async def handler(event: MessageEvent):
        await webpage.msg_arrived(
            event.msg["msg"],
            event.msg.peer_id
        )

    return handler


def MessageConnHandler(finalizing_event, msg_dispatcher, this_peer):
    """
    Iterates over a tcp stream
    if some data event occurs then calls data_dispatcher and submits that event

    Args:
    """
    receiver = MessageRecvLoopBackHandler(finalizing_event, msg_dispatcher)

    async def handle_duplication_conn(connection):
        conn = await _get_from_pool(connection.peer)
        if conn is not None:
            # no duplicate connections allowed
            closing_connection = WireData(
                header=HEADERS.DUP_MSG_CONN,
                peer_id=this_peer.peer_id,
            )
            await WireIO.send_msg(conn.connection, closing_connection)
            return False

        ok = WireData(
            header=HEADERS.MSG_CONN_OK,
            peer_id=this_peer.peer_id,
        )

        await WireIO.send_msg(connection, ok)

        return True

    async def handler(event: ConnectionEvent):
        ok = await handle_duplication_conn(event.connection)
        if not ok:
            return

        _msg_conn_pool.add(event.connection)
        async with event.connection:
            await receiver(event)

    return handler


def MessageRecvLoopBackHandler(finalizing_event, msg_dispatcher):
    async def handler(event: ConnectionEvent):
        receiver = MsgReceiver(finalizing_event, msg_dispatcher, MsgConnection(event.connection))
        try:
            await receiver.start_receiving()
        except OSError:
            return

    return handler


def PingHandler(this_peer):
    """Handle a ping received"""

    async def handler(msg_event: MessageEvent):
        ping = msg_event.msg
        un_ping = WireData(
            header=HEADERS.UNPING,
            peer_id=this_peer.peer_id,
            msg_id=ping.msg_id,
        )
        return await msg_event.connection.send(un_ping)

    return handler


# =============
# connectors
# =============

async def _try_connecting(peer, this_peer_id) -> tuple[bool, ConnectionEvent | None]:
    connector = Connector()
    connection = await _msg_conn_pool.enter_connector(connector.connect(peer, acquire_lock=False))
    await WireIO.send_msg(
        connection,
        WireData(
            header=HEADERS.CMD_MSG_CONN,
            peer_id=this_peer_id
        )
    )
    try:
        reply = await WireIO.recv_msg(connection)
    except InvalidPacket:
        return False, None

    handshake = WireData(
        header=HEADERS.CMD_MSG_CONN_RECV_LOOP_BACK,
        peer_id=reply.peer_id
    )

    con_event = ConnectionEvent(connection, handshake)

    if reply.header == HEADERS.DUP_MSG_CONN:
        return False, con_event

    assert reply.header == HEADERS.MSG_CONN_OK, \
        f"expected -{HEADERS.MSG_CONN_OK} from {connection}, got -{reply.header}"
    return True, con_event


async def get_msg_conn(this_peer_id, conn_service, peer: RemotePeer) -> MsgConnectionNoRecv:
    if msg_connection := await _get_from_pool(peer):
        _logger.debug(f"not connection again, reusing pooled connection, peer={peer}")
        return msg_connection

    ok, conn_event = await _try_connecting(peer, this_peer_id)
    if not ok:
        _logger.debug("failed to connect")
        raise CannotConnect("try again")

    msg_conn = _msg_conn_pool.add(conn_event.connection)
    conn_service.new_connection(conn_event)
    return msg_conn


async def connect_ahead(
        peer_id,
        conn_service,
        msg_conn_service,
        peer_service,
        connectivity_checker,
):
    if sender := MsgSender.get_sender(peer_id):
        if sender.is_connected:
            _logger.debug(f"not connecting again, found message sender: {sender=!r}")
            return True
        if not sender.peer.is_online:
            _logger.debug(f"peer not online, initiating a connectivity check, peer={sender.peer!r}")
            _, what = connectivity_checker.new_check(sender.peer)
            if (await what) is False:
                _logger.debug(f"cannot reach, peer={sender.peer=!r}")
                raise CannotConnect("peer unreachable")

        await sender.connect()
        return True

    peer_obj = await peer_service.get_remote_peer(peer_id)

    _logger.debug(f"connecting for messages, peer={peer_obj}")
    sender = MsgSender(
        peer_obj,
        msg_conn_service.dispatcher.register_reply,
        partial(get_msg_conn, msg_conn_service.this_peer.peer_id, conn_service),
    )

    async with AsyncExitStack() as a_ex:
        try:
            await sender.connect()
            await a_ex.enter_async_context(sender)
            _logger.info(f"connected for messages, peer={peer_obj}")
            a_ex.pop_all()
        except OSError:
            await sender.stop()
            _logger.debug(f"failed to connect, initiating a connectivity check, peer={peer_obj}")
            return False

    _exit_stack.push_async_exit(sender)
    return True


async def send_message(msg, peer_id):
    """Sends message to peer

    Args:
        msg(str): message to send
        peer_id(str): peer id to send to
    """

    if sender := MsgSender.get_sender(peer_id):
        _logger.debug(f"found msg sender for, sending message, peer={peer_id}")
        await sender.send(
            WireData(
                header=HEADERS.CMD_TEXT,
                msg_id=use.get_unique_id(),
                msg=msg,
            )
        )
        return True
    return False


async def connect_and_send(msg, peer_id, conn_service, msg_conn_service, peer_service, connectivity_checker):
    try:
        _logger.debug(f"no msg sender found, initiating a connection, peer={peer_id}")
        await connect_ahead(
            peer_id,
            conn_service,
            msg_conn_service,
            peer_service,
            connectivity_checker,
        )
    except RemotePeerNotFound:
        return False

    return await send_message(msg, peer_id)
