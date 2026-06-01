from src.avails import RemotePeer, WireData, use
from src.core.app_events import AppEventsBus, MessageReceived
from src.transfers import HEADERS
from typing_extensions import TYPE_CHECKING

if TYPE_CHECKING:
    from src.transfers.messaging.transport import MessageTransport


@use.provide__init__
class MessageProtocol:
    app_event_bus: AppEventsBus
    transport: "MessageTransport"
    this_peer: RemotePeer

    async def send_message(self, message):
        await self.transport.send_data(
            WireData(
                header=HEADERS.CMD_TEXT,
                message=message,
                message_id=use.get_unique_id(),
                peer_id=self.this_peer.peer_id
            )
        )

    async def send_message_receipt(self, message_id):
        await self.transport.send_data(
            WireData(
                header=HEADERS.MSG_READ_RECEIPT,
                message=None,
                message_id=message_id,
                peer_id=self.this_peer.peer_id
            )
        )

    async def message_received(self, message_data, from_peer_id):
        self.app_event_bus.publish(
            MessageReceived(message_data["message"], from_peer_id, message_data["message_id"])
        )

    async def message_receipt_received(self, receipt, from_peer_id):
        self.app_event_bus.publish(
            MessageReceived(None, from_peer_id, receipt["message_id"])
        )

    async def connection_made(self, connection):
        ...

    async def connection_lost(self, exc):
        ...

