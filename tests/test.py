import asyncio
import getpass
import time
from concurrent.futures.thread import ThreadPoolExecutor
from random import randint

from kademlia import utils

from src.avails import GossipMessage, RemotePeer, WireData, const
from src.configurations import bootup, configure
from src.core import connections, get_this_remote_peer, peers, requests, set_current_remote_peer_object
from src.core import get_gossip
from src.managers import profilemanager
from src.managers.statemanager import State


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


def generate_gossip():
    message = GossipMessage(message=WireData())
    message.header = requests.REQUESTS.GOSSIP_MESSAGE
    message.id = randint(1,100000)
    message.message = input("enter message to gossip")
    message.ttl = 3
    message.created = time.time()
    print("created a gossip message", message)
    return message


async def test_gossip():
    server, transport, proto = await requests.initiate()
    message = await asyncio.get_event_loop().run_in_executor(ThreadPoolExecutor(),
                                                             func=generate_gossip)
    for i in server.protocol.router.find_neighbors(get_this_remote_peer(),k=100):
        print(i)
    # await asyncio.sleep(2)
    get_gossip().gossip_message(message)


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
    return tuple(locals().values())
