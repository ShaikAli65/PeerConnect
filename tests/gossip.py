import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from random import randint

from src.avails import GossipMessage, WireData
from src.core import get_gossip, get_this_remote_peer, requests
from src.core.transfers import PalmTreeProtocol


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
    get_gossip().gossip_message(message)


async def test_plam_tree():
    PalmTreeProtocol(
                
    )
