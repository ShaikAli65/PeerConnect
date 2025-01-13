from src.avails import DataWeaver
from src.core import Dock, peers
from src.managers.statemanager import State
from src.transfers import HANDLE
from src.webpage_handlers.handleprofiles import (
    align_profiles,
    set_selected_profile,
)
from src.webpage_handlers.pagehandle import dispatch_data


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
    response_data = DataWeaver(
        header=HANDLE.SEARCH_RESPONSE,
        content=[
            {
                "name": peer.username,
                "peerId": peer.peer_id,
                "ip": peer.ip,
            } for peer in peer_list
        ],
    )
    dispatch_data(response_data)


async def send_list(data: DataWeaver):
    print("got a send list request")
    peer_list = await peers.get_more_peers()
    print("sending list", peer_list)
    response_data = DataWeaver(
        header=HANDLE.SEARCH_RESPONSE,
        content=[
            {
                "name": peer.username,
                "ip": peer.ip,
                "id": peer.peer_id,
            } for peer in peer_list
        ],
    )
    dispatch_data(response_data)


async def connect_peer(handle_data: DataWeaver): ...


async def sync_users(handle_data: DataWeaver): ...


function_dict = {
    HANDLE.CONNECT_USER: connect_peer,
    HANDLE.SYNC_USERS: sync_users,
    HANDLE.SEND_PROFILES: align_profiles,
    HANDLE.SET_PROFILE: set_selected_profile,
    HANDLE.SEARCH_FOR_NAME: search_for_user,
    HANDLE.SEND_PEER_LIST: send_list,
}


async def handler(signal_data: DataWeaver):
    print("[HANDLE SIGNALS] handler", signal_data)
    print(signal_data)
    func = function_dict[signal_data.header]
    await func(signal_data)
