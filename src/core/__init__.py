import asyncio as _asyncio
from typing import Optional, TYPE_CHECKING

from src.avails import (
    PeerDict as _PeerDict,
    RemotePeer as _RemotePeer,
    SocketCache as _SocketCache
)


class Dock:
    connected_peers = _SocketCache()
    PROFILE_WAIT = _asyncio.Event()
    peer_list = _PeerDict()
    server_in_network = False
    state_handle = None
    protocol = None
    global_gossip = None
    _this_object: Optional[_RemotePeer] = None
    kademlia_network_server = None

    if TYPE_CHECKING:
        from .transfers import RumorMongerProtocol
        from .discover import PeerServer
        from src.managers.statemanager import StateManager

        global_gossip: RumorMongerProtocol
        kademlia_network_server: PeerServer
        state_handle: StateManager

    requests_endpoint: Optional[_asyncio.DatagramTransport] = None


def get_this_remote_peer():
    return Dock._this_object


def get_gossip():
    return Dock.global_gossip


def join_gossip(data_transport):
    from .transfers import RumorMongerProtocol, GlobalGossipMessageList
    Dock.global_gossip = RumorMongerProtocol(data_transport, GlobalGossipMessageList)
    print("joined gossip network", get_gossip())


def set_current_remote_peer_object(remote_peer):
    Dock._this_object = remote_peer

