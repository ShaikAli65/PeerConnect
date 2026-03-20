import asyncio
from typing import AsyncIterator

from src.avails import DataWeaver, const
from src.conduit import logger, webpage
from src.conduit.handleprofiles import (
    align_profiles,
    set_selected_profile,
)
from src.conduit.headers import HANDLE
from src.conduit.pagehandle import MessageFromFrontEndDispatcher
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
        HANDLE.CONNECT_USER, ConnectUserHandler(
            conn_service,
            msg_conn_service,
            peer_service,
            connectivity_checker,
        ))
    dispatcher.register_handler(HANDLE.SYNC_USERS, SyncUsersHandler(peer_list))
    dispatcher.register_handler(HANDLE.SEND_PROFILES, align_profiles)
    dispatcher.register_handler(HANDLE.SET_PROFILE, set_selected_profile)
    dispatcher.register_handler(HANDLE.SEARCH_FOR_NAME, SearchUserHandler(peer_service.kad_server))
    dispatcher.register_handler(HANDLE.SEND_PEER_LIST, SendListHandler(peer_service))
    dispatcher.register_handler(HANDLE.GOSSIP_SEARCH, GossipSearchHandler(peer_service))


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
        await webpage.search_response(data.msg_id, peer_list, type="lists")

    return search_for_user


async def _response_gather_helper(iterator: AsyncIterator, timeout):
    peer_list = []

    async def gather():
        async for peer in iterator:
            peer_list.append(peer)

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
        await webpage.search_response(data.msg_id, peer_list, type="gossip")

    return gossip_search


def SendListHandler(peer_service: PeerService):
    async def send_list(data: DataWeaver):
        logger.debug("got a send list request")
        peer_list = await peer_service.get_more_peers()
        logger.debug(f"sending list {peer_list=}")
        await webpage.search_response(data.msg_id, peer_list)

    return send_list


def ConnectUserHandler(
        conn_service,
        msg_conn_service,
        peer_service,
        connectivity_checker,
):
    async def connect_peer(handle_data: DataWeaver):
        what = await message.connect_ahead(
            handle_data.peer_id,
            conn_service,
            msg_conn_service,
            peer_service,
            connectivity_checker,
        )
        await (webpage.peer_connected if what else webpage.failed_to_reach)(handle_data.peer_id)

    return connect_peer


def SyncUsersHandler(peer_list):
    async def sync_users(_: DataWeaver):
        refreshed = []

        for peer in peer_list.values():
            if peer.is_online:
                refreshed.append(peer)

        return await webpage.sync_users(refreshed)

    return sync_users
