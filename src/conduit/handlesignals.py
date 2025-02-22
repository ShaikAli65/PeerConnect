from src.avails import BaseDispatcher, DataWeaver
from src.conduit import logger, webpage
from src.conduit.handleprofiles import (
    align_profiles,
    set_selected_profile,
)
from src.conduit.headers import HANDLE
from src.core import peers
from src.core.public import Dock
from src.managers.statemanager import State


class FrontEndSignalDispatcher(BaseDispatcher):
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def submit(self, data_weaver):
        try:
            await self.registry[data_weaver.header](data_weaver)
        except Exception as exp:
            logger.error("signal dispatcher", exc_info=exp)

    def register_all(self):
        self.registry.update({
            HANDLE.CONNECT_USER: connect_peer,
            HANDLE.SYNC_USERS: sync_users,
            HANDLE.SEND_PROFILES: align_profiles,
            HANDLE.SET_PROFILE: set_selected_profile,
            HANDLE.SEARCH_FOR_NAME: search_for_user,
            HANDLE.SEND_PEER_LIST: send_list,
        })


def _restart(): ...


def receive_restart_signal(data: DataWeaver):
    s = State("restarting", func=_restart)
    Dock.state_manager_handle.state_queue.put(s)


async def close_app():
    ...


async def search_for_user(data: DataWeaver):
    search_string = data["searchPeerInNetwork"]
    print("got a search request", search_string)
    peer_list = await peers.search_for_nodes_with_name(search_string)
    print("sending list", peer_list)
    await webpage.search_response(data.msg_id, peer_list)


async def send_list(data: DataWeaver):
    print("got a send list request")
    peer_list = await peers.get_more_peers()
    print("sending list", peer_list)
    await webpage.search_response(data.msg_id, peer_list)


async def connect_peer(handle_data: DataWeaver): ...


async def sync_users(handle_data: DataWeaver): ...
