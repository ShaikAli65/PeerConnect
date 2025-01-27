import asyncio
import time

import _path  # noqa
from src.avails import GossipMessage, WireData
from src.avails.useables import get_unique_id
from src.core import get_gossip, peers
from src.managers.statemanager import State
from src.transfers import GOSSIP
from tests.test import start_test

TEST_MESSAGE = "WHAT'S UP EVERYBODY"
TEST_USERNAME = 'test'


def generate_gossip():
    message = GossipMessage(message=WireData())
    message.header = GOSSIP.MESSAGE
    message.id = get_unique_id()
    message.message = TEST_MESSAGE
    message.ttl = 3
    message.created = time.time()
    print("created a gossip message", message)
    return message


async def test_gossip():
    await asyncio.sleep(3)
    # for _ in range(10):
    message = generate_gossip()
    get_gossip().gossip_message(message)


async def test_plam_tree():
    """"""


async def test_gossip_search_user(username=TEST_USERNAME):
    await asyncio.sleep(3)
    async for peer in peers.gossip_search(username):
        print("GOT SOME REPLY", peer)

if __name__ == "__main__":
    s7 = State("checking for gossip", test_gossip)
    s8 = State("checking for gossip search", test_gossip_search_user)
    start_test((s7,s8))
