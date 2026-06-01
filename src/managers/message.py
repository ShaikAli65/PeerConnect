"""
Provides functionality to manage messaging services between remote peers, including message
transport, protocol handling, and connection management. It handles the establishment, maintenance,
and cleanup of connections, as well as sending messages and message-related events.

"""

import logging
from contextlib import AsyncExitStack
from dataclasses import field

from src.avails import RemotePeer, use
from src.avails.exceptions import ConnectionNotFound, FailedToSend
from src.core.app_events import AppEventsBus
from src.managers.connection import ConnectionManager
from src.net.events import ConnectionContext
from src.transfers import HEADERS
from src.transfers.messaging import MessageProtocol, MessageTransport

_logger = logging.getLogger(__name__)


async def initiate(app_runtime, this_peer, connection_manager):
    return MessagingService(this_peer, connection_manager, app_runtime.app_events, AsyncExitStack())


@use.provide__init__
class MessagingService:
    _this_peer: RemotePeer
    _connection_manager: ConnectionManager
    _app_event_bus: AppEventsBus
    _exit_stack: AsyncExitStack
    _peer_connections: dict[str, tuple[MessageProtocol, MessageTransport]] = field(default_factory=dict)

    def __post_init__(self):
        self._connection_manager.connection_router.register_handler(
            HEADERS.CMD_MSG_CONN, self.msg_connection_arrived
        )

    async def msg_connection_arrived(self, event_ctx: ConnectionContext):
        event = await self._exit_stack.enter_async_context(event_ctx)
        try:
            protocol, transport = self._peer_connections[event.handshake.peer_id]
            _logger.debug(f"new msg connection, peer={event.handshake.peer_id}, updating existing message transport")
            transport.connection_made(event.connection)
        except KeyError:
            self._peer_connections[event.handshake.peer_id] = protocol, transport = self._prepare_pair(event.connection)
            await self._exit_stack.enter_async_context(transport.context_manager())
            _logger.debug(f"new msg connection, peer={event.handshake.peer_id}, creating message protocol, transport pair")

    async def close_pooled_connection(self, remote_peer):
        pair = self._peer_connections.pop(remote_peer.peer_id, None)
        if pair is None:
            return
        await self._connection_manager.close_connection(pair[0].transport.connection)

    async def send_message(self, msg, remote_peer, retry_connecting=True):
        return await self._send_message_helper(
            MessageProtocol.send_message,
            msg,
            remote_peer,
            retry_connecting,
        )

    async def send_message_read_receipt(self, msg_id, peer_id, retry_connecting=True):
        return await self._send_message_helper(
            MessageProtocol.send_message_receipt,
            msg_id,
            peer_id,
            retry_connecting,
        )

    async def ensure_connection(self, remote_peer):
        try:
            protocol, transport = self._peer_connections[remote_peer.peer_id]

        except (KeyError, ConnectionError):
            connection = await self._exit_stack.enter_async_context(
                self._connection_manager.get_connection(remote_peer)
            )
            self._peer_connections[remote_peer.peer_id] = p = self._prepare_pair(connection)
            return p

    def _prepare_pair(self, connection):
        protocol = MessageProtocol(self._app_event_bus, None, self._this_peer)
        transport = MessageTransport(protocol)
        transport.connection_made(connection)
        protocol.transport = transport
        return protocol, transport

    async def _send_message_helper(
          self,
          send_message_function,
          msg,
          remote_peer,
          try_connecting=True,
    ):

        try:
            protocol, transport = self._peer_connections[remote_peer.peer_id]
        except KeyError:
            if not try_connecting:
                raise ConnectionNotFound(remote_peer.peer_id)

            protocol, transport = await self.ensure_connection(remote_peer)

        try:
            return await send_message_function(protocol, msg)
        except FailedToSend as fts:
            if not try_connecting:
                raise fts

        protocol, transport = await self.ensure_connection(remote_peer)
        return await send_message_function(protocol, msg)
