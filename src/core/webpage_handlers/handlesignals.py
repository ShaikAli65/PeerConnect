import websockets

from src.avails import DataWeaver
from src.avails.useables import awaitable
from src.core import state_handle
from src.core.webpage_handlers.handleprofiles import align_profiles
from src.managers.statemanager import State

HANDLE_SEND_PROFILE = 'send profiles'


def restart():

    ...


def receive_restart_signal(data):
    s = State('restarting',func=restart)
    state_handle.state_queue.put(s)

    ...


async def handler(data:DataWeaver, websocket: websockets.WebSocketServerProtocol):
    print("handlesignals handler", data)

    if data.match_header(HANDLE_SEND_PROFILE):
        await align_profiles(websocket)


