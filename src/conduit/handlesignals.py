import asyncio
from typing import AsyncIterator

from src.avails import BaseDispatcher, DataWeaver, const
from src.avails.mixins import CallHandlerMixIn
from src.conduit import logger, webpage
from src.conduit.handleprofiles import (
    align_profiles,
    set_selected_profile,
)
from src.conduit.headers import HANDLE
from src.core import peers
from src.managers import message


class FrontEndSignalDispatcher(BaseDispatcher, CallHandlerMixIn):
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def submit(self, data_weaver):  # type: ignore
        return await self.call_handler(
            data_weaver.header,
            logger,
            data_weaver,
        )

    def register_all(self):
        self.registry.update({
            HANDLE.CONNECT_USER: connect_peer,
            HANDLE.SYNC_USERS: sync_users,  # TODO: fix this
            HANDLE.SEND_PROFILES: align_profiles,
            HANDLE.SET_PROFILE: set_selected_profile,
            HANDLE.SEARCH_FOR_NAME: search_for_user,
            HANDLE.SEND_PEER_LIST: send_list,  # TODO: fix this
            HANDLE.GOSSIP_SEARCH: gossip_search
        })


async def close_app():
    ...


async def search_for_user(kad_server, data: DataWeaver):
    search_string = data.content
    if search_string == "":
        logger.debug("skipping search request, content contains empty key")
        return

    # TODO: fix this
    logger.info(f"got a search request: {search_string}")
    peer_list = await _response_gather_helper(
        peers.search_for_peers_with_name(search_string, kad_server=kad_server),
        const.TIMEOUT_TO_GATHER_SEARCH_RESULTS
    )
    await webpage.search_response(data.msg_id, peer_list, type="lists")


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


async def gossip_search(data: DataWeaver):
    search_string = data.content
    if search_string == "":
        logger.debug("skipping search request, content contains empty string")
        return
    logger.info(f"got a gossip search request: {search_string}")
    peer_list = await _response_gather_helper(
        peers.gossip_search(search_string),
        const.TIMEOUT_TO_GATHER_SEARCH_RESULTS
    )
    await webpage.search_response(data.msg_id, peer_list, type="gossip")


async def send_list(kad_server, data: DataWeaver):
    logger.debug("got a send list request")
    peer_list = await peers.get_more_peers(kad_server)
    logger.debug(f"sending list {peer_list=}")
    await webpage.search_response(data.msg_id, peer_list)


async def connect_peer(handle_data: DataWeaver):
    # TODO: fix this
    what = await message.connect_ahead(peer_id=handle_data.peer_id)
    await (webpage.peer_connected if what else webpage.failed_to_reach)(handle_data.peer_id)


async def sync_users(peer_list, _: DataWeaver):
    refreshed = []

    for peer in peer_list.values():
        if peer.is_online:
            refreshed.append(peer)

    return await webpage.sync_users(refreshed)
