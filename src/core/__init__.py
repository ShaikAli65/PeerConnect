import asyncio as _asyncio
from typing import Optional, TYPE_CHECKING

from src.avails import (
    PeerDict as _PeerDict,
    RemotePeer as _RemotePeer,
    SocketCache as _SocketCache
)


class Dock:
    connected_peers = _SocketCache()
    peer_list = _PeerDict()
    server_in_network = False
    state_handle = None
    protocol = None
    global_gossip = None
    _this_object: Optional[_RemotePeer] = None
    kademlia_network_server = None
    finalizing = _asyncio.Event()
    if TYPE_CHECKING:
        from src.core.transfers import RumorMongerProtocol
        from src.core._kademlia import PeerServer
        from src.managers.statemanager import StateManager

        global_gossip: RumorMongerProtocol
        kademlia_network_server: PeerServer
        state_handle: StateManager

    requests_endpoint: Optional[_asyncio.DatagramTransport] = None


def get_this_remote_peer():
    return Dock._this_object


def get_gossip():
    return Dock.global_gossip


def set_current_remote_peer_object(remote_peer):
    Dock._this_object = remote_peer

