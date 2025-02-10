import asyncio
import getpass
import os
import random
import sys

from kademlia import utils

import _path  # noqa
import main
import src
from src import managers
from src.avails import RemotePeer, const
from src.avails.connect import UDPProtocol
from src.configurations import bootup, configure
from src.core import Dock, acceptor, connectivity, requests, set_current_remote_peer_object
from src.managers import ProfileManager, profilemanager
from src.managers.statemanager import State
from src.webpage_handlers import pagehandle, webpage


def _create_listen_socket_mock(bind_address, _):
    loop = asyncio.get_running_loop()
    sock = UDPProtocol.create_async_server_sock(
        loop, bind_address, family=const.IP_VERSION
    )
    print("mocked socket creation")
    return sock


async def _mock_interface_selector(interfaces):
    print("not asking for", (i := next(iter(interfaces))))
    return i


webpage.ask_for_interface_choice = _mock_interface_selector


# async def setup_request_transport(bind_address, multicast_address, req_dispatcher):
#     loop = asyncio.get_running_loop()
#     base_socket = _create_listen_socket(bind_address, multicast_address)
#     transport, proto = await loop.create_datagram_endpoint(
#         functools.partial(RequestsEndPoint, req_dispatcher),
#         sock=base_socket
#     )
#     req_dispatcher.transport = RequestsTransport(transport)
#     return transport


def test():
    requests._create_listen_socket = _create_listen_socket_mock
    const.THIS_IP = '127.0.0.' + sys.argv[1]
    const.SERVER_IP = const.THIS_IP
    const.MULTICAST_IP_v4 = '127.0.0.1'
    const.PORT_NETWORK = 4000
    const.DISCOVER_RETRIES = 1
    set_current_remote_peer_object(
        RemotePeer(
            byte_id=utils.digest(f"{const.THIS_IP}{const.PORT_THIS}"),
            username=f"test-{getpass.getuser()}",
            ip=const.THIS_IP,
            conn_port=const.PORT_THIS,
            req_port=const.PORT_REQ,
            status=1,
        )
    )
    # print(peers.get_this_remote_peer())


def get_a_peer() -> RemotePeer | None:
    try:
        p = next(iter(Dock.peer_list))
    except StopIteration:
        print("no peers available")
        return None
    return p


async def profile_getter():
    p = await ProfileManager.add_profile(
        getpass.getuser(),
        {
            "USER": {
                "name": getpass.getuser(),
                "id": random.getrandbits(255),
            },
            "SERVER": {
                "port": 45000,
                "ip": "0.0.0.0",
                "id": 0,
            },
            "INTERFACE": {}
        }
    )

    async def delete(*_):
        await ProfileManager.delete_profile(p.file_name)

    Dock.exit_stack.push_async_exit(delete)
    return p


async def mock_profile():
    src.managers.profilemanager._current_profile = await profile_getter()


def mock_multicast():
    const.MULTICAST_IP_v4 = "172.16.210.0"
    # const.MULTICAST_IP_v4 = '172.16.196.238'
    const.PORT_NETWORK = 4000
    requests._create_listen_socket = _create_listen_socket_mock


def test_initial_states():
    # :todo: look into states once again
    s1 = State("set paths", configure.set_paths)
    s2 = State("loading configurations", configure.load_configs)
    s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    s4 = State("launching webpage", pagehandle.initiate_page_handle)
    s5 = State("mocking profile", mock_profile)
    s6 = State("boot up", bootup.initiate_bootup)
    s7 = State("configuring this remote peer object", bootup.configure_this_remote_peer)
    s8 = State("printing configurations", configure.print_constants)
    s9 = State("initiating requests", requests.initiate)
    s10 = State("initiating comms", acceptor.initiate_acceptor, is_blocking=True)
    s11 = State("connectivity checker", connectivity.initiate)
    return tuple(locals().values())


def start_test(other_states):
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    main.initiate(test_initial_states() + tuple(other_states))


if __name__ == "__main__":
    # print(isinstance(RequestsDispatcher, AbstractDispatcher))
    start_test([])
