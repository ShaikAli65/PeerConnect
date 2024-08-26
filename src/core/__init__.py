import asyncio as _asyncio

from .peers import get_this_remote_peer, set_current_remote_peer_object
from .peers import peer_list
from ..avails import SocketCache as _SocketCache
from ..managers.profilemanager import get_current_profile
from ..managers.statemanager import StateManager
from . import requests


connected_peers = _SocketCache()
state_handle = StateManager()
PROFILE_WAIT = _asyncio.Event()

__all__ = [
    'requests',
    'get_current_profile',
    'StateManager',
    'get_this_remote_peer',
    'set_current_remote_peer_object',
    'peer_list',
    'PROFILE_WAIT',
    'connected_peers',
    'state_handle',
]
