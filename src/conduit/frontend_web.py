import asyncio
from typing import runtime_checkable

from conduit import headers
from conduit.pagehandle import FrontEndMessagesDispatcher, FrontEndWebSockets
from src.avails.exceptions import InvalidPacket
from src.conduit import ui_codec
from src.conduit.bases import AnyUIError, AnyUINotification, AnyUIPrompt, AnyUIPromptReply, AnyUIResult, \
    FrontEnd, UIPromptReply
from src.conduit.ui_codec import DataWeaver
from transfers.abc import AbstractTransferHandle, TransferEvents


@runtime_checkable
class WebFrontend(FrontEnd):
    """Frontend Abstraction for Web UI"""

    def __init__(self, sender: FrontEndWebSockets, receiver: FrontEndMessagesDispatcher):
        self.sender = sender
        self.receiver = receiver

    def send_data_to_frontend(self, data, expect_reply=False) -> asyncio.Future[DataWeaver] | None:
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


class WebpageTransferEvents(TransferEvents):
    def __init__(self, web_frontend: WebFrontend):
        self.web_frontend = web_frontend

    async def transfer_started(self, transfer: AbstractTransferHandle):
        pass

    async def transfer_update(self, transfer_handle: AbstractTransferHandle):
        # TODO: use `TransferStatusChanged` and `TransferUpdate` from ui_events for all of the below methods
        status_update = DataWeaver(
            header=headers.TRANSFER_UPDATE,
            content={
                'item_path': str(transfer_handle.current_transfer.path),
                'progress': transfer_handle.status_updater.current_status,
                'transfer_id': transfer_handle.id,
            },
            peer_id=transfer_handle.peer.peer_id,
        )
        self.web_frontend.send_data_to_frontend(status_update)

    async def transfer_completed(self, transfer: AbstractTransferHandle):
        pass

    async def transfer_incomplete(self, transfer_handle: AbstractTransferHandle, error):
        content = {
            'transfer_id': transfer_handle.id,
            'cancelled': True,
        }
        if transfer_handle.current_transfer is not None:
            content.update(
                {
                    'item_path': str(transfer_handle.current_transfer.path),
                    'progress': transfer_handle.status_updater.current_status,
                })

        content.update({'error': str(error)} if error else {})

        status_update = DataWeaver(
            header=headers.TRANSFER_UPDATE,
            content=content,
            peer_id=transfer_handle.peer.peer_id,
        )
        self.web_frontend.send_data_to_frontend(status_update)

    async def transfer_confirmation(self, transfer_handle: AbstractTransferHandle, confirmation_details):
        dw = DataWeaver(
            header=headers.TRANSFER_UPDATE,
            content={"confirmation": confirmation_details, 'transferId': transfer_handle.id},
            peer_id=transfer_handle.peer.peer_id,
        )
        self.web_frontend.send_data_to_frontend(dw)
