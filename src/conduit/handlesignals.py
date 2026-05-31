import asyncio
from typing import AsyncIterator

from conduit import ui_events
from conduit.bases import FrontEnd
from conduit.frontend_web import WebFrontend
from managers.message import MessagingService
from src.avails import const
from src.conduit import logger, ui_codec
from src.conduit.ui_codec import DataWeaver
from src.conduit.ui_events import ConnectPeer, GossipSearchPeers, PeerConnectionStatus, PeerSummary, \
    RequestPeerList, \
    RequestUsersSync, \
    SearchPeersByName, SearchResults, \
    UsersSnapshot
from src.core.peers import PeerListGetter, PeerService


def handlers_to_register(
      msg_conn_service,
      peer_service,
      frontend: WebFrontend,
):
    return [
        (ConnectPeer, ConnectUserHandler(msg_conn_service, peer_service, frontend)),
        (RequestUsersSync, SyncUsersHandler(peer_service, frontend)),
        (SearchPeersByName, SearchUserHandler(peer_service.kad_server, frontend)),
        (RequestPeerList, SendListHandler(peer_service, frontend)),
        (GossipSearchPeers, GossipSearchHandler(peer_service, frontend)),
    ]


def SearchUserHandler(peer_service: PeerService, frontend: FrontEnd):
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
        frontend.send_result(SearchResults(peer_list, ui_events.SearchSource.LIST, data.msg_id))

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


def GossipSearchHandler(peer_service: PeerService, frontend: FrontEnd):
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
        frontend.send_result(
            SearchResults(peer_list, ui_events.SearchSource.GOSSIP, data.msg_id)
        )

    return gossip_search


def SendListHandler(peer_service: PeerService, frontend: FrontEnd):
    async def send_list(data: DataWeaver):
        logger.debug("got a send list request")
        peer_list = await PeerListGetter.get_more_peers(peer_service.kad_server)
        logger.debug(f"sending list {peer_list=}")
        frontend.send_result(SearchResults(
            [ui_codec.remote_peer_to_peer_summary(peer) for peer in peer_list]
            if peer_list else [],
            ui_events.SearchSource.GOSSIP,
            data.msg_id
        ))

    return send_list


def ConnectUserHandler(
      msg_conn_service: MessagingService,
      peer_service,
      frontend: FrontEnd
):
    async def connect_peer(connect_peer_req: ConnectPeer):
        peer = await peer_service.get_remote_peer(connect_peer_req.peer_id)
        connection_pair = await msg_conn_service.ensure_connection(peer)
        frontend.notify(PeerConnectionStatus(connect_peer_req.peer_id, bool(connection_pair)))

    return connect_peer


def SyncUsersHandler(peer_service, frontend: FrontEnd):
    async def sync_users(_: ui_events.RequestPeerList):
        refreshed = []

        for peer in peer_service.peer_list.values():
            refreshed.append(
                PeerSummary(
                    name=peer.username,
                    ip=peer.ip,
                    peer_id=peer.peer_id,
                    online=peer.online,
                ))

        frontend.send_result(UsersSnapshot(refreshed))

    return sync_users
