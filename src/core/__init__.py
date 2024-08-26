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


class REQUESTS:
    __slots__ = ()
    REDIRECT = b'redirect        '
    LIST_SYNC = b'sync list       '
    ACTIVE_PING = b'Y face like that'
    REQ_FOR_LIST = b'list of users  '
    I_AM_ACTIVE = b'com notify user'
    NETWORK_FIND = b'network find    '
    NETWORK_FIND_REPLY = b'network find reply '


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
    'REQUESTS',
]
