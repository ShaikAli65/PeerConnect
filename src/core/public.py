import asyncio as _asyncio
from contextlib import AsyncExitStack
from enum import IntEnum
from typing import Optional, TYPE_CHECKING

from src.avails import BaseDispatcher, InvalidPacket, PeerDict as _PeerDict, RemotePeer as _RemotePeer, WireData, \
    constants as _const


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
    in_network = _asyncio.Event()  # this gets set when we are in network and unset if not
    finalizing = _asyncio.Event()
    requests_transport = None
    dispatchers: dict[DISPATCHS, BaseDispatcher] = {}
    exit_stack = AsyncExitStack()
    if TYPE_CHECKING:
        from src.transfers import RumorMongerProtocol
        from src.transfers.transports import RequestsTransport
        from src.core._kademlia import PeerServer
        from src.managers.statemanager import StateManager
        peer_list: _PeerDict[str, _RemotePeer]
        global_gossip: RumorMongerProtocol
        kademlia_network_server: PeerServer
        state_manager_handle: StateManager
        requests_transport: RequestsTransport


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


async def send_msg_to_requests_endpoint(msg: WireData, peer, *, expect_reply=False):
    """Send a msg to requests endpoint of the peer

    Notes:
        if expect_reply is True and no msg_id available in msg raises InvalidPacket
    Args:
        msg(WireData): message to send
        peer(RemotePeer): msg is sent to
        expect_reply(bool): waits until a reply is arrived with the same id as the msg packet
    Raises:
        InvalidPacket: if msg does not contain msg_id and expecting a reply
    """
    if msg.msg_id is None and expect_reply is True:
        raise InvalidPacket("msg_id not found and expecting a reply")

    Dock.requests_transport.sendto(bytes(msg), peer.req_uri)

    if expect_reply:
        req_disp = requests_dispatcher()
        return await req_disp.register_reply(msg.msg_id)


if TYPE_CHECKING:
    from src.core.requests import RequestsDispatcher
    from src.core.acceptor import ConnectionDispatcher
    from src.core.discover import DiscoveryDispatcher
    from src.core.gossip import GossipDispatcher
    from src.managers.message import MsgDispatcher


    def requests_dispatcher() -> RequestsDispatcher: ...


    def discover_dispatcher() -> DiscoveryDispatcher: ...


    def gossip_dispatcher() -> GossipDispatcher: ...


    def connections_dispatcher() -> ConnectionDispatcher: ...


    def msg_dispatcher() -> MsgDispatcher: ...
