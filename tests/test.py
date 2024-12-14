import asyncio
import getpass
import os
import sys

from kademlia import utils

sys.path.append("C:\\Users\\7862s\\Desktop\\PeerConnect\\")

from src.avails import RemotePeer, const
from src.configurations import bootup, configure
from src.core import Dock, connections, requests, set_current_remote_peer_object
from src.managers import profilemanager
from src.managers.statemanager import State, StateManager


async def fake_search_network():
    if len(sys.argv) >= 2:
        return '127.0.0.' + sys.argv[1], const.PORT_NETWORK


def test():
    requests.search_network = fake_search_network
    if len(sys.argv) >= 3:
        const.THIS_IP = '127.0.0.' + sys.argv[2]
    else:
        const.THIS_IP = '127.0.0.1'
    const.SERVER_IP = const.THIS_IP
    const.PORT_SERVER = 45000
    set_current_remote_peer_object(
        RemotePeer(
            peer_id=utils.digest(const.THIS_IP + str(const.PORT_THIS)),
            username=f"test-{getpass.getuser()}",
            ip=const.THIS_IP,
            conn_port=const.PORT_THIS,
            req_port=const.PORT_REQ,
            net_port=const.PORT_NETWORK,
            status=1,
        )
    )
    # print(peers.get_this_remote_peer())


def test_initial_states():
    s1 = State("setpaths", configure.set_paths)
    s2 = State("boot_up initiating", bootup.initiate_bootup)
    s3 = State("adding shit", test)
    s4 = State("loading profiles", profilemanager.load_profiles_to_program)
    s5 = State("printing configurations", configure.print_constants)
    s6 = State("intitating requests", requests.initiate)
    s9 = State("initiating comms", connections.initiate_connections, is_blocking=True)
    return tuple(locals().values())


async def initiate(states):
    Dock.state_handle = StateManager()
    await Dock.state_handle.put_states(states)
    await Dock.state_handle.process_states()


if __name__ == '__main__':
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    asyncio.run(initiate(test_initial_states()), debug=True)
