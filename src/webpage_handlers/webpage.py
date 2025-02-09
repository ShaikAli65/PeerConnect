from src.avails import DataWeaver, RemotePeer
from src.webpage_handlers import headers
from src.webpage_handlers.pagehandle import front_end_data_dispatcher


async def ask_user_for_a_peer():
    reply = await front_end_data_dispatcher(
        DataWeaver(
            header=headers.REQ_PEER_NAME_FOR_DISCOVERY,
        ),
        expect_reply=True,
    )
    return reply.content.get('peerName', None)


async def failed_to_reach(peer):
    front_end_data_dispatcher(
        DataWeaver(header=headers.FAILED_TO_REACH, content={"peer": peer})
    )


async def update_peer(peer):
    data = DataWeaver(
        header=headers.NEW_PEER if peer.status == RemotePeer.ONLINE else headers.REMOVE_PEER,
        content={
            "name": peer.username,
            "ip": peer.ip,
        },
        peer_id=peer.peer_id,
    )
    front_end_data_dispatcher(data)


async def get_transfer_ok(peer_id):
    confirmation = await front_end_data_dispatcher(
        DataWeaver(
            header=headers.REQ_FOR_FILE_TRANSFER,
            peer_id=peer_id,
        ),
        expect_reply=True
    )
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


async def search_response(search_id, peer_list):
    response_data = DataWeaver(
        header=headers.SEARCH_RESPONSE,
        content=[
            {
                "name": peer.username,
                "ip": peer.ip,
                "peerId": peer.peer_id,
            } for peer in peer_list
        ],
        msg_id=search_id,
    )
    front_end_data_dispatcher(response_data)


async def send_profiles_and_get_updated_profiles(profiles):
    userdata = DataWeaver(header=headers.PEER_LIST, content=profiles)
    return (await front_end_data_dispatcher(userdata, expect_reply=True)).content
