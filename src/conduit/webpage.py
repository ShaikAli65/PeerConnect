from src.avails import use
from src.conduit import headers, ui_codec
from src.conduit.pagehandle import send_data_to_frontend
from src.conduit.ui_codec import DataWeaver
from src.conduit.ui_events_bases import AnyUIError, AnyUINotification, AnyUIPrompt, AnyUIPromptReply, AnyUIResult, \
    UIPromptReply


async def failed_to_send_message(message_id, peer_id):
    send_data_to_frontend(DataWeaver(  # noqa
        header=headers.FAILED_TO_SEND,
        peer_id=peer_id,
        msg_id=message_id
    ))


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


def _json_peer(peer):
    return {
        "name": peer.username,
        "ip": peer.ip,
        "peerId": peer.peer_id,
    }


async def failed_to_reach(peer_id):
    send_data_to_frontend(  # noqa
        DataWeaver(header=headers.FAILED_TO_REACH, peer_id=peer_id)
    )


async def update_peer(peer):
    data = DataWeaver(
        header=headers.NEW_PEER if peer.is_online else headers.REMOVE_PEER,
        content=_json_peer(peer),
        peer_id=peer.peer_id,
    )
    send_data_to_frontend(data)  # noqa


async def get_transfer_ok(profile, peer_id):
    if (agreed := profile.transfers_agreed.get(peer_id, None)) is not None:
        return agreed

    confirmation = await send_data_to_frontend(  # noqa
        DataWeaver(
            header=headers.REQ_FOR_FILE_TRANSFER,
            peer_id=peer_id,
            msg_id=use.get_unique_id(str),
        ),
        expect_reply=True,
    )

    if (remember := confirmation.content["remember"]) is not None:
        await profile.add_transfers_agreed(peer_id, remember)

    return bool(confirmation.content['confirmed'])


async def transfer_confirmation(transfer_handle, confirmation):
    send_data_to_frontend(  # noqa
        DataWeaver(
            header=headers.TRANSFER_UPDATE,
            content={"confirmation": confirmation, 'transferId': transfer_handle.id},
            peer_id=transfer_handle.peer.peer_id,
        )
    )


async def transfer_update(transfer_handle):
    status_update = DataWeaver(
        header=headers.TRANSFER_UPDATE,
        content={
            'item_path': str(transfer_handle.current_file.path),
            'progress': transfer_handle.status_updater.current_status,
            'transfer_id': transfer_handle.id,
        },
        peer_id=transfer_handle.peer.peer_id,
    )
    send_data_to_frontend(status_update)  # noqa


async def transfer_incomplete(transfer_handle, detail=None):
    content = {
        'transfer_id': transfer_handle.id,
        'cancelled': True,
    }
    if transfer_handle.current_file is not None:
        content.update(
            {
                'item_path': str(transfer_handle.current_file.path),
                'progress': transfer_handle.status_updater.current_status,
            })

    content.update({'error': str(detail)} if detail else {})

    status_update = DataWeaver(
        header=headers.TRANSFER_UPDATE,
        content=content,
        peer_id=transfer_handle.peer.peer_id,
    )
    send_data_to_frontend(status_update)  # noqa


async def send_profiles_and_get_updated_profiles(profiles, interfaces):
    userdata = DataWeaver(
        header=headers.PEER_LIST,
        content={
            "profiles": profiles,
            "interfaces": [getattr(v, '_asdict')() for v in interfaces]
        },
        msg_id=use.get_unique_id(str)
    )

    return (await send_data_to_frontend(userdata, expect_reply=True)).content  # noqa


def notify(message: AnyUINotification):
    send_data_to_frontend(ui_codec.encode_event(event=message))


def send_error(error: AnyUIError):
    send_data_to_frontend(ui_codec.encode_event(event=error))


async def send_prompt_and_get_response(prompt: AnyUIPrompt) -> AnyUIPromptReply:
    resp_data = await send_data_to_frontend(
        ui_codec.encode_event(event=prompt),
        expect_reply=True
    )
    prompt_resp = ui_codec.decode_data(resp_data)
    assert isinstance(prompt_resp, UIPromptReply), f"expected UIPromptReply, got {prompt_resp=}"
    return prompt_resp


def send_result(result: AnyUIResult):
    send_data_to_frontend(ui_codec.encode_event(event=result))
