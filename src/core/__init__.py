import asyncio as _asyncio
from typing import Optional

from .peers import peer_list
from .peers import this_object
from ..avails import SocketCache as _SocketCache
from . import requests
from ..managers import ProfileManager as _pm
from ..managers.statemanager import StateManager

connected_peers = _SocketCache()
state_handle = StateManager()

PROFILE_WAIT = _asyncio.Event()
PAGE_HANDLE_WAIT = _asyncio.Event()
current_profile: Optional[_pm] = None
