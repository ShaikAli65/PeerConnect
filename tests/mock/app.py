import asyncio
from configparser import ConfigParser
from typing import TYPE_CHECKING

from src.avails import PeerDict
from src.avails.mixins import AggregatingAsyncExitStack
from src.core._kademlia import PeerServer
from src.core.app import _ClassLevelDesc, _Connections, _Discovery, _GlobalGossip, _Messages, _RemotePeerDesc, \
    _Requests
from src.managers import ProfileManager
from src.managers.statemanager import StateManager
from src.net import IPAddress


class MockApp(metaclass=_ClassLevelDesc):
    gossip = _GlobalGossip
    requests = _Requests
    discovery = _Discovery
    connections = _Connections
    messages = _Messages

    exit_stack = AggregatingAsyncExitStack()
    # exit_stack = AsyncExitStack()
    this_ip = None
    this_remote_peer = _RemotePeerDesc()
    this_peer_id: str = None
    kad_server: PeerServer = None
    in_network = asyncio.Event()
    finalizing = asyncio.Event()
    peer_list = PeerDict()
    current_config: ConfigParser = None
    current_profile: ProfileManager = None
    state_manager_handle: StateManager = None
    interfaces: list[IPAddress] = None
    __instance = None

    @classmethod
    def addr_tuple(cls, ip, port):
        return cls.this_ip.addr_tuple(port=port, ip=ip)

    @classmethod
    def read_only(cls):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)  # Create an instance
            cls.__instance.__init__()
            return cls.__instance
        return cls.__instance

    def __new__(cls, *args, **kwargs):
        raise TypeError("use App.read_only to create instances")

    def __init__(self):
        # make read only
        self.__dict__["gossip"] = self.gossip()
        self.__dict__["requests"] = self.requests()
        self.__dict__["discovery"] = self.discovery()
        self.__dict__["connections"] = self.connections()
        self.__dict__["messages"] = self.messages()


if TYPE_CHECKING:
    from src.core.app import App


    class MockApp(App):
        pass
