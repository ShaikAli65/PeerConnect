import asyncio
import time
import logging

from src.avails import const, RemotePeer
from src.configurations import configure, bootup
from src.core import connectserver, connections, requests
from src.core.peers import set_current_remote_peer_object
from src.managers import profilemanager
from src.managers.statemanager import State
from src.managers import filemanager

from src.core import peers


def test():
    const.SERVER_IP = const.THIS_IP
    const.PORT_SERVER = 45000
    set_current_remote_peer_object(
        RemotePeer(
            'test',
            ip=const.THIS_IP,
            conn_port=const.PORT_THIS,
            req_port=const.PORT_REQ,
            net_port=const.PORT_NETWORK,
        )
    )
    # print(peers.get_this_remote_peer())


async def test_gossip():
    requests_data = await requests.initiate()
    gossip_message = {'message': 'hi for all', 'ttl':3}
    await asyncio.sleep(8)
    print('sending gossip message\a')
    await requests_data[0].protocol.call_gossip(gossip_message)


def test_initial_states():
    s1 = State("setpaths", configure.set_paths)
    s2 = State("boot_up initiating", bootup.initiate_bootup)
    s3 = State("adding shit", test)
    s4 = State("loading profiles", profilemanager.load_profiles_to_program)
    s5 = State("printing configurations", configure.print_constants)
    # s4 = State("connecting to servers",connectserver.initiate_connection)
    # s4 = State("connecting to servers",connectserver.initiate_connection)
    s6 = State("checking for gossip", test_gossip)
    s7 = State("initiating comms", connections.initiate_connections, is_blocking=True)

    return tuple(locals().values())
