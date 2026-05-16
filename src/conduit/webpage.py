import asyncio
import asyncio as _asyncio

from src.avails import use
from src.avails.exceptions import InvalidPacket
from src.conduit import headers
from src.conduit.ui_codec import DataWeaver


def send_data_to_frontend(data, expect_reply=False) -> _asyncio.Future[DataWeaver] | asyncio.Task:
    """Send a packet to frontend based on type code

    Args:
        data(DataWeaver): packet to send
        expect_reply: if expecting a reply, this function returns an asyncio.Future

    Returns:
        Future[DataWeaver] | Task

    Raises:
        InvalidPacket: if msg does not contain msg_id and expecting a reply

    """
    from src.conduit.pagehandle import FrontEndConnector, FrontEndMessagesDispatcher

    disp = FrontEndConnector()
    msg_disp = FrontEndMessagesDispatcher()

    r = disp(data)

    if expect_reply:
        if data.msg_id is None:
            raise InvalidPacket("msg_id not found and expecting a reply")

        return msg_disp.register_reply(data.msg_id)

    return r


async def ask_user_peer_name_for_discovery(reason):
    reply = await send_data_to_frontend(  # noqa
        DataWeaver(
            header=headers.REQ_PEER_NAME_FOR_DISCOVERY,
            content={"reason": reason},
            msg_id=use.get_unique_id(str)
        ),
        expect_reply=True,
    )
    return reply.content.get('peerName', None)

#
# def _json_peer(peer):
#     return {
#         "name": peer.username,
#         "ip": peer.ip,
#         "peerId": peer.peer_id,
#     }


async def failed_to_reach(peer_id):
    send_data_to_frontend(
        DataWeaver(header=headers.FAILED_TO_REACH, peer_id=peer_id)
    )

#
# async def send_profiles_and_get_updated_profiles(profiles, interfaces):
#     userdata = DataWeaver(
#         header=headers.PEER_LIST,
#         content={
#             "profiles": profiles,
#             "interfaces": [getattr(v, '_asdict')() for v in interfaces]
#         },
#         msg_id=use.get_unique_id(str)
#     )
#
#     return (await send_data_to_frontend(userdata, expect_reply=True)).content  # noqa
#
#
# def notify(message: AnyUINotification):
#     send_data_to_frontend(ui_codec.encode_event(event=message))
#
#
# def send_error(error: AnyUIError):
#     send_data_to_frontend(ui_codec.encode_event(event=error))
#
#
# async def send_prompt_and_get_response(
#       prompt: AnyUIPrompt,
#       resp_type: type[AnyUIPromptReply] = None
# ) -> AnyUIPromptReply:
#     resp_data = await send_data_to_frontend(
#         ui_codec.encode_event(event=prompt),
#         expect_reply=True
#     )
#     prompt_resp = ui_codec.decode_data(resp_data)
#     assert isinstance(prompt_resp, UIPromptReply), f"expected UIPromptReply, got {prompt_resp=}"
#     return prompt_resp
#
#
# def send_result(result: AnyUIResult):
#     send_data_to_frontend(ui_codec.encode_event(event=result))
