import asyncio as _asyncio
from asyncio import DatagramTransport
from typing import Optional

import kademlia.network

from . import transfers, webpage_handlers
from ..avails import PeerDict, RemotePeer, SocketCache as _SocketCache
from ..managers.profilemanager import get_current_profile
from ..managers.statemanager import StateManager


class Dock:
    state_handle = StateManager()
    connected_peers = _SocketCache()
    PROFILE_WAIT = _asyncio.Event()
    peer_list = PeerDict()
    server_in_network = False
    _this_object: Optional[RemotePeer] = None
    kademlia_network_server: Optional[kademlia.network.Server] = None
    requests_endpoint: Optional[DatagramTransport] = None
    protocol = None


def get_this_remote_peer():
    return Dock._this_object


def set_current_remote_peer_object(remote_peer):
    Dock._this_object = remote_peer


__all__ = [
    'requests',
    'get_current_profile',
    'StateManager',
    'get_this_remote_peer',
    'set_current_remote_peer_object',
    'Dock',
    'transfers',
    'webpage_handlers',
]