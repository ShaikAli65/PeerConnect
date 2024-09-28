import websockets

from src.avails import DataWeaver
from src.core import Dock, peers
from src.core.webpage_handlers.handleprofiles import align_profiles
from src.managers.statemanager import State

HANDLE_SEND_PROFILE = 'send profiles'
HANDLE_SEND_PEER_LIST = 'send peer list'
HANDLE_SEARCH_FOR_NAME = 'search name'
HANDLE_SEARCH_RESPONSE = 'result for search name'
HANDLE_SEND_PEER_LIST_RESPONSE = 'result for send peer list'


def restart():

    ...


def receive_restart_signal(data):
    s = State('restarting',func=restart)
    Dock.state_handle.state_queue.put(s)


async def search_for_user(data, websocket):
    search_string = data['search_string']
    print('got a search request', search_string)
    peer_list = await peers.search_for_nodes_with_name(search_string)
    print('sending list', peer_list)
    response_data = DataWeaver(
        header=HANDLE_SEARCH_RESPONSE,
        content=[{'name': peer.username, 'id': peer.id} for peer in peer_list],
    )
    await websocket.send(response_data.dump())


async def send_list(data: DataWeaver, websocket):
    print('got a send list request')
    peer_list = await peers.get_more_peers()
    print('sending list', peer_list)
    response_data = DataWeaver(
        header=HANDLE_SEARCH_RESPONSE,
        content=[{'name': peer.username, 'id': peer.id} for peer in peer_list],
    )
    await websocket.send(response_data.dump())


async def handler(data:str, websocket: websockets.WebSocketServerProtocol):
    print("handlesignals handler", data)
    data = DataWeaver(serial_data=data)
    if data.match_header(HANDLE_SEND_PROFILE):
        await align_profiles(websocket)
    elif data.match_header(HANDLE_SEND_PEER_LIST):
        await send_list(data, websocket)
    elif data.match_header(HANDLE_SEARCH_FOR_NAME):
        await search_for_user(data, websocket)
    elif data.match_header(b''):
        ...
