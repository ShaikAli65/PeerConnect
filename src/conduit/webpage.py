from src.avails import DataWeaver, use
from src.conduit import headers
from src.conduit.pagehandle import front_end_data_dispatcher
from src.managers import ProfileManager


async def ask_for_interface_choice(interfaces):
    reply = await front_end_data_dispatcher(
        DataWeaver(
            header=headers.GET_INTERFACE_CHOICE,
            content={k: getattr(v, "_asdict")() for k, v in interfaces}
        ),
        expect_reply=True
    )
    return reply.content.get("interface_id", None)


async def msg_arrived(header, message, peer_id):
    front_end_data_dispatcher(DataWeaver(
        header=header,
        content=message,
        peer_id=peer_id,
    ))


async def ask_user_peer_name_for_discovery(reason):
    reply = await front_end_data_dispatcher(
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
    front_end_data_dispatcher(
        DataWeaver(header=headers.FAILED_TO_REACH, peer_id=peer_id)
    )


async def peer_connected(peer_id):
    front_end_data_dispatcher(
        DataWeaver(header=headers.PEER_CONNECTED, peer_id=peer_id)
    )


async def update_peer(peer):
    data = DataWeaver(
        header=headers.NEW_PEER if peer.is_online else headers.REMOVE_PEER,
        content=_json_peer(peer),
        peer_id=peer.peer_id,
    )
    front_end_data_dispatcher(data)


async def get_transfer_ok(profile: ProfileManager, peer_id):
    if (agreed := profile.transfers_agreed.get(peer_id, None)) is not None:
        return agreed

    confirmation = await front_end_data_dispatcher(
        DataWeaver(
            header=headers.REQ_FOR_FILE_TRANSFER,
            peer_id=peer_id,
        ),
        expect_reply=True
    )

    if (remember := confirmation.content["remember"]) is not None:
        await profile.add_transfers_agreed(peer_id, remember)

    return bool(confirmation.content['confirmed'])


async def transfer_confirmation(peer_id, transfer_id, confirmation):
    front_end_data_dispatcher(
        DataWeaver(
            header=headers.TRANSFER_UPDATE,
            content={"confirmation": confirmation, 'transferId': transfer_id},
            peer_id=peer_id,
        )
    )


async def transfer_update(peer_id, transfer_id, file_item):
    status_update = DataWeaver(
        header=headers.TRANSFER_UPDATE,
        content={
            'item_path': str(file_item.path),
            'received': file_item.seeked,
            'transfer_id': transfer_id,
        },
        peer_id=peer_id,
    )
    front_end_data_dispatcher(status_update)


async def transfer_incomplete(peer_id, transfer_id, file_item, detail=None):
    content = {
        'transfer_id': transfer_id,
        'cancelled': True,
    }
    if file_item is not None:
        content.update({'item_path': str(file_item.path),
                        'received': file_item.seeked,
                        })

    content.update({'error': str(detail)} if detail else {})

    status_update = DataWeaver(
        header=headers.TRANSFER_UPDATE,
        content=content,
        peer_id=peer_id,
    )
    front_end_data_dispatcher(status_update)


async def search_response(search_id, peer_list, type="lists"):
    response_data = DataWeaver(
        header=headers.SEARCH_RESPONSE if type == "lists" else headers.GOSSIP_SEARCH_RESPONSE,
        content=[_json_peer(peer) for peer in peer_list] if peer_list else [],
        msg_id=search_id,
    )
    front_end_data_dispatcher(response_data)


async def send_profiles_and_get_updated_profiles(profiles, interfaces):
    userdata = DataWeaver(
        header=headers.PEER_LIST,
        content={
            "profiles": profiles,
            "interfaces": [getattr(v, '_asdict')() for v in interfaces]
        },
        msg_id=use.get_unique_id(str)
    )

    return (await front_end_data_dispatcher(userdata, expect_reply=True)).content


async def sync_users(peer_list):
    return front_end_data_dispatcher(
        DataWeaver(
            header=headers.SYNC_USERS,
            content=[
                _json_peer(peer) for peer in peer_list
            ],
        )
    )
