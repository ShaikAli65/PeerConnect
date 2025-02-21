import asyncio as _asyncio
from contextlib import AsyncExitStack
from enum import IntEnum
from typing import Optional, TYPE_CHECKING

from src.avails import (
    BaseDispatcher, PeerDict as _PeerDict,
    RemotePeer as _RemotePeer,
    const as _const
)


class DISPATCHS(IntEnum):
    REQUESTS = 1
    DISCOVER = 2
    GOSSIP = 3
    CONNECTIONS = 4
    MESSAGES = 5


class Dock:
    """Global references, grouped at one place"""
    peer_list = _PeerDict()
    state_manager_handle = None
    global_gossip = None
    _this_object: Optional[_RemotePeer] = None
    kademlia_network_server = None
    finalizing = _asyncio.Event()
    requests_transport: Optional[_asyncio.DatagramTransport] = None
    dispatchers: dict[DISPATCHS, BaseDispatcher] = {}
    exit_stack = AsyncExitStack()
    if TYPE_CHECKING:
        from src.transfers import RumorMongerProtocol
        from src.core._kademlia import PeerServer
        from src.managers.statemanager import StateManager
        peer_list: _PeerDict[str, _RemotePeer]
        global_gossip: RumorMongerProtocol
        kademlia_network_server: PeerServer
        state_manager_handle: StateManager


def addr_tuple(ip, port):
    return _const.THIS_IP.addr_tuple(port=port, ip=ip)


def get_this_remote_peer():
    return Dock._this_object


def get_gossip():
    return Dock.global_gossip


def get_dispatcher(dispatcher_id):
    return Dock.dispatchers[dispatcher_id]


def set_current_remote_peer_object(remote_peer):
    Dock._this_object = remote_peer


# dispatcher helpers

def requests_dispatcher():  # = 1
    return Dock.dispatchers.get(DISPATCHS.REQUESTS)


def discover_dispatcher():  # = 2
    return Dock.dispatchers.get(DISPATCHS.DISCOVER)


def gossip_dispatcher():  # = 3
    return Dock.dispatchers.get(DISPATCHS.GOSSIP)


def connections_dispatcher():  # = 4
    return Dock.dispatchers.get(DISPATCHS.CONNECTIONS)


def msg_dispatcher():  # = 5
    return Dock.dispatchers.get(DISPATCHS.MESSAGES)
