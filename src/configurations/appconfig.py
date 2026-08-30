import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any

from src.avails import PeerDict, const, use
from src.avails.mixins import AggregatingAsyncExitStack
from src.core.app_events import AppEventsBus
from src.managers import ProfileManager
from src.net import Interface, NetworkProtocol, TCPProtocol


class Versions:
    Global: str = const.VERSIONS["GLOBAL"]
    RemotePeer: str = const.VERSIONS["RP"]
    FileObject: str = const.VERSIONS["FO"]
    DirectoryObject: str = const.VERSIONS["DO"]
    WireProto: str = const.VERSIONS["WIRE"]


@dataclass
class AppConfig:
    """
    Represents the configuration settings for an application.

    Attributes:
        selected_profile (ProfileManager): The profile manager associated with
            the application's current configuration.
        ip_version (int): The Internet Protocol version being used. Defaults to
            const.IP_VERSION.
        protocol (type[NetworkProtocol]): The protocol class used for network
            communication. Defaults to TCPProtocol.
        this_port (int): The port used for the application's primary services.
            Defaults to const.PORT_THIS.
        req_port (int): The port used for request handling.
            Defaults to const.PORT_REQ.
        page_port (int): The port used by the UI to communicate with application.
            Defaults to const.PORT_PAGE.
        page_serve_port (int): UI is hosted here.
            Defaults to const.PORT_PAGE_SERVE.
        version (Versions): Contains version-related information about the
            application.
    """
    selected_profile: ProfileManager
    ip_version: int = const.IP_VERSION
    protocol: type[NetworkProtocol] = TCPProtocol
    this_port: int = const.PORT_THIS
    req_port: int = const.PORT_REQ
    page_port: int = const.PORT_PAGE
    page_serve_port: int = const.PORT_PAGE_SERVE
    version: type[Versions] = Versions


@use.provide__init__(slots=True)
class AppRunTime:
    """Represents the runtime context of the application.

    Encapsulates various runtime state variables and objects
    required for the application to operate.

    Wrapper for variables necessary for coordination during the application's lifecycle.

    Attributes:
        profiles (list[ProfileManager]): A list of all profiles
            configured for the runtime.
        finalizing (asyncio.Event): An asyncio event that signals whether
            the application is in the process of finalizing its operations.
        in_network (asyncio.Event): An asyncio event that indicates whether
            the application is currently connected to a network.
        peer_list (PeerDict): A dictionary of peers participating in the
            network, indexed by identifiers.
        interfaces (list[Interface]): A list of network interfaces available
            for communication.
        exit_stack (contextlib.AsyncExitStack[Any]): An asynchronous
            context stack used for managing the lifecycle of resources
            during the application runtime.
    """
    profiles: list[ProfileManager]
    finalizing: asyncio.Event
    in_network: asyncio.Event
    peer_list: PeerDict
    interfaces: list[Interface]
    exit_stack: contextlib.AsyncExitStack[Any]
    app_events: AppEventsBus


def init_app_runtime():
    return AppRunTime(
        profiles=[],
        finalizing=(asyncio.Event()),
        in_network=(asyncio.Event()),
        peer_list=(PeerDict()),
        interfaces=[],
        exit_stack=(AggregatingAsyncExitStack()),
        app_events=(AppEventsBus()),
    )
