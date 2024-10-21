import asyncio as _asyncio
from typing import Optional


from src.avails import (
    PeerDict as _PeerDict,
    RemotePeer as _RemotePeer,
    SocketCache as _SocketCache
)


import kademlia.network
type server = kademlia.network.Server
# from src.core.discover import PeerServer
# type server = PeerServer


class Dock:
    connected_peers = _SocketCache()
    PROFILE_WAIT = _asyncio.Event()
    peer_list = _PeerDict()
    server_in_network = False
    state_handle = None
    protocol = None
    global_gossip = None
    _this_object: Optional[_RemotePeer] = None

    kademlia_network_server: Optional[server] = None
    requests_endpoint: Optional[_asyncio.DatagramTransport] = None


def get_this_remote_peer():
    return Dock._this_object  # noqa


def get_gossip():
    return Dock.global_gossip


def join_gossip(kademlia_server):
    from .transfers import RumorMongerProtocol, GlobalGossipMessageList
    Dock.global_gossip = RumorMongerProtocol(GlobalGossipMessageList)
    get_gossip().initiate()


def set_current_remote_peer_object(remote_peer):
    Dock._this_object = remote_peer
