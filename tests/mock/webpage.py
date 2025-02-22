from contextlib import asynccontextmanager

from src.avails import constants
from src.conduit import pagehandle
from src.managers import get_current_profile


@asynccontextmanager
async def mock_start_websocket_server():
    yield


def mock_webpage():
    profile = get_current_profile()
    constants.WEBSOCKET_BIND_IP = profile.interface.ip
    pagehandle.start_websocket_server = mock_start_websocket_server
