from sys import stderr

from src.avails import DataWeaver, use
from src.core import Dock, peers
from src.core.webpage_handlers.handleprofiles import align_profiles, set_selected_profile
from src.core.webpage_handlers.pagehandle import dispatch_data
from src.managers.statemanager import State
from src.core.transfers import HEADERS


def restart():

    ...


def receive_restart_signal(data: DataWeaver):
    s = State('restarting',func=restart)
    Dock.state_manager_handle.state_queue.put(s)


async def search_for_user(data: DataWeaver):
    search_string = data['search_string']
    print('got a search request', search_string)
    peer_list = await peers.search_for_nodes_with_name(search_string)
    print('sending list', peer_list)
    response_data = DataWeaver(
        header=HEADERS.HANDLE_SEARCH_RESPONSE,
        content=[{'name': peer.username, 'id': peer.id} for peer in peer_list],
    )
    dispatch_data(response_data)


async def send_list(data: DataWeaver):
    print('got a send list request')
    peer_list = await peers.get_more_peers()
    print('sending list', peer_list)
    response_data = DataWeaver(
        header=HEADERS.HANDLE_SEARCH_RESPONSE,
        content=[{'name': peer.username, 'id': peer.id} for peer in peer_list],
    )
    dispatch_data(response_data)


async def connect_peer(handle_data: DataWeaver):
    ...


async def sync_users(handle_data: DataWeaver):
    ...


function_dict = {
    HEADERS.HANDLE_CONNECT_USER: connect_peer,
    HEADERS.HANDLE_SYNC_USERS: sync_users,
    HEADERS.HANDLE_SEND_PROFILES: align_profiles,
    HEADERS.HANDLE_SET_PROFILE: set_selected_profile,
    HEADERS.HANDLE_SEARCH_FOR_NAME:search_for_user,
    HEADERS.HANDLE_SEND_PEER_LIST: send_list,
}


async def handler(signal_data:DataWeaver):
    print("handlesignals handler", signal_data)
    func = handler
    try:
        func = function_dict[signal_data.header]
        await func(signal_data)
    except Exception as exp:
        print(f"Got an exception at handlesignals - {use.func_str(func)}", exp, file=stderr)
        raise
