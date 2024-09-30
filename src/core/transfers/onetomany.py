import asyncio
import math
from collections import defaultdict

from src.avails import RemotePeer, const
from ..connections import Connector


def next_power_of_two(n):
    if n < 1:
        return 1
    return 2 ** math.ceil(math.log2(n))


class SendBytesToMultiplePeers:
    def __init__(self, data: bytes, peers: list[RemotePeer], session_id):
        self.data = data
        self.peer_list = peers
        self.adjacency_list = defaultdict(list)
        self.max_no_peers = next_power_of_two(len(peers))
        self.dimensions = self.max_no_peers.bit_length() - 1
        self.session_id = session_id

    async def start(self):
        """Start the process of sending data to peers."""
        self.create_hypercube()
        await self.inform_peers()

    def create_hypercube(self):
        """Create the hypercube topology."""
        peer_id_to_peer_mapping = {i: peer for i, peer in zip(range(len(self.peer_list)), self.peer_list)}
        for i in range(len(self.peer_list)):
            for j in range(self.dimensions):
                neighbor = i ^ (1 << j)
                if neighbor < len(self.peer_list):
                    peer = peer_id_to_peer_mapping[j]
                    neigh = peer_id_to_peer_mapping[neighbor]
                    self.adjacency_list[peer.id].append(neigh.id)

    async def inform_peers(self):
        tasks = []
        for peer in self.peer_list:
            tasks.append(self.contact_peer(peer))

        requested_peers = await asyncio.gather(*tasks, return_exceptions=False)

    async def contact_peer(self, peer):
        peer_connection = await Connector.connect_peer(peer)

