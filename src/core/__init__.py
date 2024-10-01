import asyncio as _asyncio
from typing import Optional

import kademlia.network

from src.avails import (
    PeerDict as _PeerDict,
    RemotePeer as _RemotePeer,
    SocketCache as _SocketCache
)


class Dock:
    state_handle = None
    connected_peers = _SocketCache()
    PROFILE_WAIT = _asyncio.Event()
    peer_list = _PeerDict()
    server_in_network = False
    _this_object: Optional[_RemotePeer] = None
    kademlia_network_server: Optional[kademlia.network.Server] = None
    requests_endpoint: Optional[_asyncio.DatagramTransport] = None
    protocol = None
    global_gossip = None


def get_this_remote_peer():
    return Dock._this_object


def get_gossip():
    return Dock.global_gossip


async def join_gossip(kademlia_server):
    get_gossip().initiate()


def set_current_remote_peer_object(remote_peer):
    Dock._this_object = remote_peer
