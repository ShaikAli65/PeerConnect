import asyncio
from configparser import ConfigParser
from contextlib import AsyncExitStack
from typing import Callable, Concatenate, ParamSpec, TypeVar, Union

from src.avails import PeerDict, RemotePeer
from src.avails.connect import IPAddress
from src.core._kademlia import PeerServer
from src.core.acceptor import ConnectionDispatcher
from src.core.discover import DiscoveryDispatcher
from src.core.gossip import GlobalRumorMonger, GossipDispatcher
from src.core.requests import RequestsDispatcher
from src.managers import ProfileManager
from src.managers.message import MsgDispatcher
from src.managers.statemanager import StateManager
from src.transfers import GossipTransport
from src.transfers.transports import DiscoveryTransport, RequestsTransport


class _NoSetter:
    __slots__ = ()

    def __setattr__(self, item, value):
        raise NotImplementedError("not allowed to set")


class _GlobalGossip(_NoSetter):
    __slots__ = ()
    dispatcher: GossipDispatcher
    transport: GossipTransport
    gossiper: GlobalRumorMonger


class _Requests(_NoSetter):
    __slots__ = ()
    dispatcher: RequestsDispatcher
    transport: RequestsTransport


class _Connections(_NoSetter):
    __slots__ = ()
    dispatcher: ConnectionDispatcher


class _Messages(_NoSetter):
    __slots__ = ()
    dispatcher: MsgDispatcher


class _Discovery(_NoSetter):
    __slots__ = ()
    dispatcher: DiscoveryDispatcher
    transport: DiscoveryTransport


class _RemotePeerDesc: ...


class App(_NoSetter):
    __slots__ = ()

    gossip = _GlobalGossip
    requests = _Requests
    discovery = _Discovery
    connections = _Connections
    messages = _Messages

    exit_stack: AsyncExitStack
    this_ip: IPAddress
    this_remote_peer: RemotePeer
    kad_server: PeerServer
    in_network: asyncio.Event
    finalizing: asyncio.Event
    peer_list: PeerDict
    current_config: ConfigParser
    current_profile: ProfileManager
    state_manager_handle: StateManager
    interfaces: list[IPAddress]
    this_peer_id: str | int
    __instance = None

    @classmethod
    def addr_tuple(cls, ip, port) -> IPAddress: ...

    @classmethod
    def read_only(cls) -> App: ...


AppType = type[App]

ReadOnlyAppType = App


def get_app_context() -> ReadOnlyAppType: ...


P = ParamSpec("P")
R = TypeVar("R")

Args = Union[Concatenate[P, ReadOnlyAppType], P]


def provide_app_ctx(func: Callable[P, R]) -> Callable[Args, R]: ...
