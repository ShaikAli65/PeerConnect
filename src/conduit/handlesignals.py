import asyncio
from typing import AsyncIterator

from src.avails import const
from src.conduit import logger, ui_codec, webpage
from src.conduit.handleprofiles import (
    align_profiles,
    set_selected_profile,
)
from src.conduit.pagehandle import MessageFromFrontEndDispatcher
from src.conduit.ui_codec import DataWeaver
from src.conduit.ui_events import ConnectPeer, GossipSearchPeers, PeerConnectionStatus, PeerSummary, RequestPeerList, \
    RequestProfilesSync, \
    RequestUsersSync, \
    SearchPeersByName, SearchResults, \
    SetSelectedProfile, UsersSnapshot
from src.core.peers import PeerService
from src.managers import message


def register_handlers(
        dispatcher: MessageFromFrontEndDispatcher,
        conn_service,
        msg_conn_service,
        peer_service,
        connectivity_checker,
        peer_list,

):
    dispatcher.register_handler(
        ConnectPeer.event_name(), ConnectUserHandler(
            conn_service,
            msg_conn_service,
            peer_service,
            connectivity_checker,
        ))
    dispatcher.register_handler(RequestUsersSync.event_name(), SyncUsersHandler(peer_list))
    dispatcher.register_handler(RequestProfilesSync.event_name(), align_profiles)
    dispatcher.register_handler(SetSelectedProfile.event_name(), set_selected_profile)
    dispatcher.register_handler(SearchPeersByName.event_name(), SearchUserHandler(peer_service.kad_server))
    dispatcher.register_handler(RequestPeerList.event_name(), SendListHandler(peer_service))
    dispatcher.register_handler(GossipSearchPeers.event_name(), GossipSearchHandler(peer_service))


def SearchUserHandler(peer_service: PeerService):
    async def search_for_user(data: DataWeaver):
        search_string = data.content
        if search_string == "":
            logger.debug("skipping search request, content contains empty key")
            return

        logger.info(f"got a search request: {search_string}")
        peer_list = await _response_gather_helper(
            peer_service.search_for_peers_with_name(search_string),
            const.TIMEOUT_TO_GATHER_SEARCH_RESULTS
        )
        webpage.send_result(SearchResults(peer_list, "list", data.msg_id))

    return search_for_user


async def _response_gather_helper(iterator: AsyncIterator, timeout):
    peer_list = []

    async def gather():
        async for peer in iterator:
            peer_list.append(ui_codec.remote_peer_to_peer_summary(peer))

    t = asyncio.create_task(gather())
    try:
        await asyncio.wait_for(t, timeout)
    except TimeoutError:
        pass
    return peer_list


def GossipSearchHandler(peer_service: PeerService):
    async def gossip_search(data: DataWeaver):
        search_string = data.content
        if search_string == "":
            logger.debug("skipping search request, content contains empty string")
            return
        logger.info(f"got a gossip search request: {search_string}")
        peer_list = await _response_gather_helper(
            peer_service.gossip_search(search_string),
            const.TIMEOUT_TO_GATHER_SEARCH_RESULTS
        )
        webpage.send_result(
            SearchResults(peer_list, "gossip", data.msg_id)
        )

    return gossip_search


def SendListHandler(peer_service: PeerService):
    async def send_list(data: DataWeaver):
        logger.debug("got a send list request")
        peer_list = await peer_service.get_more_peers()
        logger.debug(f"sending list {peer_list=}")
        webpage.send_result(SearchResults(
            [ui_codec.remote_peer_to_peer_summary(peer) for peer in peer_list]
            if peer_list else [],
            "list",
            data.msg_id
        ))

    return send_list


def ConnectUserHandler(
        conn_service,
        msg_conn_service,
        peer_service,
        connectivity_checker,
):
    async def connect_peer(connect_peer_req: ConnectPeer):
        what = await message.connect_ahead(
            connect_peer_req.peer_id,
            conn_service,
            msg_conn_service,
            peer_service,
            connectivity_checker,
        )
        webpage.notify(PeerConnectionStatus(connect_peer_req.peer_id, what))
    return connect_peer


def SyncUsersHandler(peer_list):
    async def sync_users(_: DataWeaver):
        refreshed = []

        for peer in peer_list.values():
            refreshed.append(
                PeerSummary(
                    name=peer.username,
                    ip=peer.ip,
                    peer_id=peer.peer_id,
                    online=peer.online,
                ))

        webpage.send_result(UsersSnapshot(refreshed))

    return sync_users
