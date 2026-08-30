import asyncio
from typing import Awaitable, TYPE_CHECKING

from src.avails import use
from src.avails.exceptions import InvalidPacket
from src.conduit import ui_codec
from src.conduit.bases import AnyUIError, AnyUINotification, AnyUIPrompt, AnyUIPromptReply, AnyUIResult, \
    UIPromptReply
from src.conduit.ui_codec import DataWeaver
from src.conduit.ui_events import (
    DecideIncomingTransfer,
    DiscoveryPeerNameRequested,
    IncomingTransferDecisionRequested,
    ProvideDiscoveryPeerName,
)

if TYPE_CHECKING:
    from src.conduit.pagehandle import FrontEndMessagesDispatcher, FrontEndWebSockets


class WebFrontend:  # protocol impl: FrontEnd
    """Frontend Abstraction for Web UI"""

    def __init__(self, sender: "FrontEndWebSockets", receiver: "FrontEndMessagesDispatcher"):
        self.sender = sender
        self.receiver = receiver

    def send_data_to_frontend(self, data, expect_reply=False) -> Awaitable[DataWeaver] | None:
        """Send a packet to frontend based on type code

        Args:
            data(DataWeaver): packet to send
            expect_reply: if expecting a reply, this function returns an asyncio.Future

        Returns:
            Future[DataWeaver] | Task

        Raises:
            InvalidPacket: if msg does not contain msg_id and expecting a reply

        """

        r = self.sender.send_message(data)

        if expect_reply:
            if data.msg_id is None:
                raise InvalidPacket("msg_id not found and expecting a reply")

            return self.receiver.register_reply(data.msg_id)

        return r

    def notify(self, message: AnyUINotification):
        self.send_data_to_frontend(ui_codec.encode_event(event=message))

    def send_error(self, error: AnyUIError):
        self.send_data_to_frontend(ui_codec.encode_event(event=error))

    async def send_prompt_and_get_response(self,
                                           prompt: AnyUIPrompt,
                                           resp_type: type[AnyUIPromptReply] | None = None
                                           ) -> AnyUIPromptReply:
        resp_data = await self.send_data_to_frontend(
            ui_codec.encode_event(event=prompt),
            expect_reply=True
        )
        prompt_resp = ui_codec.decode_data(resp_data)
        assert isinstance(prompt_resp, UIPromptReply), f"expected UIPromptReply, got {prompt_resp=}"
        return prompt_resp

    def send_result(self, result: AnyUIResult):
        self.send_data_to_frontend(ui_codec.encode_event(event=result))

    @property
    def frontend_websockets(self):
        return self.sender

    @property
    def frontend_messages_dispatcher(self):
        return self.receiver


class WebUserPrompts:  # protocol impl: UserPrompts
    def __init__(self, frontend: WebFrontend):
        self.frontend = frontend

    async def ask_discovery_peer_name(self, reason: str) -> str | None:
        reply = await self.frontend.send_prompt_and_get_response(
            DiscoveryPeerNameRequested(use.get_unique_id(str), reason),
            ProvideDiscoveryPeerName,
        )
        return reply.peer_name

    async def ask_transfer_consent(self, peer_id: str) -> tuple[bool, bool | None]:
        confirmation = await self.frontend.send_prompt_and_get_response(
            IncomingTransferDecisionRequested(use.get_unique_id(str), peer_id), DecideIncomingTransfer
        )
        return confirmation.confirmed, confirmation.remember
