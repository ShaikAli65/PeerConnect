import asyncio
import os
import sys
import time


sys.path.append("C:\\Users\\7862s\\Desktop\\PeerConnect\\")

from src.avails.useables import get_unique_id
from src.managers.statemanager import State
from test import initiate, test_initial_states
from src.avails import GossipMessage, WireData
from src.core import get_gossip, peers
from src.core.transfers import REQUESTS_HEADERS
from src.avails import const

TEST_MESSAGE = "WHAT'S UP EVERYBODY"
TEST_USERNAME = 'test'


def generate_gossip():
    message = GossipMessage(message=WireData())
    message.header = REQUESTS_HEADERS.GOSSIP_MESSAGE
    message.id = get_unique_id()
    message.message = TEST_MESSAGE
    message.ttl = 3
    message.created = time.time()
    print("created a gossip message", message)
    return message


async def test_gossip():
    # for _ in range(10):
    message = generate_gossip()
    get_gossip().gossip_message(message)


async def test_plam_tree():
    """"""


async def test_gossip_search_user(username=TEST_USERNAME):
    async for peer in peers.gossip_search(username):
        print("GOT SOME REPLY", peer)

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    i_states = test_initial_states()
    s7 = State("checking for gossip", test_gossip)
    s8 = State("checking for gossip search", test_gossip_search_user)
    states = i_states + (s7, s8)
    asyncio.run(initiate(states), debug=True)
