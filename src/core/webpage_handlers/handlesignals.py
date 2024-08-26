import websockets

from src.avails import DataWeaver
from src.core import state_handle
from src.core import peers
from src.core.webpage_handlers.handleprofiles import align_profiles
from src.managers.statemanager import State

HANDLE_SEND_PROFILE = 'send profiles'
HANDLE_SEND_PEER_LIST = 'send peer list'


def restart():

    ...


def receive_restart_signal(data):
    s = State('restarting',func=restart)
    state_handle.state_queue.put(s)

    ...


async def send_list(data: DataWeaver):
    last_node_id = data.content

    pass


async def handler(data:str, websocket: websockets.WebSocketServerProtocol):
    print("handlesignals handler", data)
    data = DataWeaver(serial_data=data)
    if data.match_header(HANDLE_SEND_PROFILE):
        await align_profiles(websocket)
    elif data.match_header(HANDLE_SEND_PEER_LIST):
        await send_list(data)
    elif data.match_header():
