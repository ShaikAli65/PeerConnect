import asyncio as _asyncio
from enum import IntEnum
from typing import Optional, TYPE_CHECKING

from src.avails import (
    BaseDispatcher, PeerDict as _PeerDict,
    RemotePeer as _RemotePeer, SocketCache as _SocketCache
)


class DISPATCHS(IntEnum):
    REQUESTS = 1
    DISCOVER = 2
    GOSSIP = 3


class Dock:
    connected_peers = _SocketCache()
    peer_list = _PeerDict()
    state_manager_handle = None
    global_gossip = None
    _this_object: Optional[_RemotePeer] = None
    kademlia_network_server = None
    finalizing = _asyncio.Event()
    requests_endpoint: Optional[_asyncio.DatagramTransport] = None
    dispatchers: dict[DISPATCHS, BaseDispatcher] = {}

    if TYPE_CHECKING:
        from src.core.transfers import RumorMongerProtocol
        from src.core._kademlia import PeerServer
        from src.managers.statemanager import StateManager
        peer_list: _PeerDict[str, _RemotePeer]
        global_gossip: RumorMongerProtocol
        kademlia_network_server: PeerServer
        state_manager_handle: StateManager


def get_this_remote_peer():
    return Dock._this_object


def get_gossip():
    return Dock.global_gossip


def get_dispatcher(dispatcher_id):
    return Dock.dispatchers[dispatcher_id]


def set_current_remote_peer_object(remote_peer):
    Dock._this_object = remote_peer
