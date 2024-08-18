import asyncio as _asyncio
from typing import Optional

from .peers import peer_list
from .peers import get_this_remote_peer
from ..avails import SocketCache as _SocketCache
from . import requests
from ..managers.profilemanager import get_current_profile
from ..managers.statemanager import StateManager

connected_peers = _SocketCache()
state_handle = StateManager()

PROFILE_WAIT = _asyncio.Event()
PAGE_HANDLE_WAIT = _asyncio.Event()
