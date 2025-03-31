import asyncio
from typing import AsyncIterator

from src.avails import BaseDispatcher, DataWeaver, const
from src.conduit import logger, webpage
from src.conduit.handleprofiles import (
    align_profiles,
    set_selected_profile,
)
from src.conduit.headers import HANDLE
from src.core import peers
from src.core.app import ReadOnlyAppType, provide_app_ctx
from src.managers import message
from src.managers.statemanager import State


class FrontEndSignalDispatcher(BaseDispatcher):
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def submit(self, data_weaver):
        try:
            handler = self.registry[data_weaver.header]
            logger.debug(f"invoking page signal handler {handler}")
            await handler(data_weaver)
        except Exception as exp:
            logger.error(f"signal dispatcher data:{data_weaver}", exc_info=exp)

    def register_all(self):
        self.registry.update({
            HANDLE.CONNECT_USER: connect_peer,
            HANDLE.SYNC_USERS: sync_users,
            HANDLE.SEND_PROFILES: align_profiles,
            HANDLE.SET_PROFILE: set_selected_profile,
            HANDLE.SEARCH_FOR_NAME: search_for_user,
            HANDLE.SEND_PEER_LIST: send_list,
            HANDLE.GOSSIP_SEARCH: gossip_search
        })


def _restart(): ...


def receive_restart_signal(app_ctx, data: DataWeaver):
    s = State("restarting", func=_restart)
    app_ctx.state_manager_handle.state_queue.put(s)


async def close_app():
    ...


async def search_for_user(data: DataWeaver):
    search_string = data.content
    if search_string == "":
        logger.debug("skipping search request, content contains empty key")
        return

    peer_list = await _response_gather_helper(
        peers.search_for_peers_with_name(search_string),
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


async def send_list(data: DataWeaver):
    print("got a send list request")
    peer_list = await peers.get_more_peers()
    print("sending list", peer_list)
    await webpage.search_response(data.msg_id, peer_list)


async def connect_peer(handle_data: DataWeaver):
    what = await message.connect_ahead(peer_id=handle_data.peer_id)
    await (webpage.peer_connected if what else webpage.failed_to_reach)(handle_data.peer_id)


@provide_app_ctx
async def sync_users(_: DataWeaver, *, app_ctx: ReadOnlyAppType = None):
    refreshed = []

    for peer in app_ctx.peer_list.values():
        if peer.is_online:
            refreshed.append(peer)

    return await webpage.sync_users(refreshed)
