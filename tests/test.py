import asyncio
import getpass
from concurrent.futures.thread import ThreadPoolExecutor

from kademlia import utils

from src.avails import RemotePeer, const
from src.configurations import bootup, configure
from src.core import connections, peers, requests, set_current_remote_peer_object
from src.managers import profilemanager
from src.managers.statemanager import State
from tests.file import test_file_transfer


def test():
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


async def test_list_of_peers():
    while True:
        await asyncio.get_event_loop().run_in_executor(ThreadPoolExecutor(),func=lambda: input("enter"))
        peer_list = await peers.get_more_peers()
        print(peer_list)


def test_initial_states():
    s1 = State("setpaths", configure.set_paths)
    s2 = State("boot_up initiating", bootup.initiate_bootup)
    s3 = State("adding shit", test)
    s4 = State("loading profiles", profilemanager.load_profiles_to_program)
    s5 = State("printing configurations", configure.print_constants)
    s6 = State("intitating requests",    requests.initiate)
    # s4 = State("connecting to servers",connectserver.initiate_connection)
    # s6 = State("checking for gossip", test_gossip)
    s7 = State("checking for peer gathering", test_list_of_peers, is_blocking=True)
    s8 = State("initiating comms", connections.initiate_connections, is_blocking=True)
    s9 = State("test file transfer", test_file_transfer, is_blocking=True)
    return tuple(locals().values())
