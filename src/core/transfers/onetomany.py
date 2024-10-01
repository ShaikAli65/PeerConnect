import asyncio
import itertools
import math
from collections import defaultdict
from dataclasses import dataclass

from src.avails import RemotePeer, WireData, const, unpack_datagram
from . import HEADERS
from ..connections import Connector
from .. import get_this_remote_peer


def next_power_of_two(n):
    if n < 1:
        return 1
    return 2 ** math.ceil(math.log2(n))


class SendOTMBytes:
    def __init__(self, data: bytes, peers: list[RemotePeer], session_id):
        self.data = data
        self.peer_list = peers.append(get_this_remote_peer())
        self.adjacency_list = defaultdict(list)
        self.max_no_peers = next_power_of_two(len(peers))
        self.dimensions = self.max_no_peers.bit_length() - 1
        self.session_id = session_id
        self.confirmed_peers = None

    async def start(self):
        """Start the process of sending data to peers."""
        self.create_hypercube()
        await self.inform_peers()
        await self.trigger_spanning_formation()

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
        tasks = [self.contact_peer(peer) for peer in self.peer_list]
        requested_peers = await asyncio.gather(*tasks, return_exceptions=False)
        self.confirmed_peers = list(itertools.takewhile(lambda x:x[1], requested_peers))
        # send an audit event to page confirming peers

    async def contact_peer(self, peer):
        peer_connection = await Connector.connect_peer(peer)
        await peer_connection.asendall(self.prepare_request(peer))
        return peer, True

    def prepare_request(self, peer):
        return WireData(
            header=HEADERS.CMD_RECV_FILE_AND_FORWARD,
            _id=get_this_remote_peer().id,
            session_id=self.session_id,
            session_token=self.session_token,
            adjacent_peers=self.adjacency_list[peer.id],
        ).__bytes__()

    async def trigger_spanning_formation(self):

        pass

    @property
    def session_token(self):
        return "test"  # :todo perform a cipher algorithm


@dataclass
class OTMSession:
    originater_id: str
    adjacent_peers: list[str]
    session_id: int
    session_token: str
    active_edge: str = None

    def start_passive_receiver(self):
        loop = asyncio.get_event_loop()
        loop.create_datagram_endpoint(
            protocol_factory=lambda:OTMPassiveProtocol(self),
            family=const.IP_VERSION,
        )


class OTMPassiveProtocol(asyncio.DatagramProtocol):

    def __init__(self, otm_session: OTMSession):
        self.otm_session = otm_session

    def datagram_received(self, data, addr):
        data = unpack_datagram(data)
        print("got some data at passive endpoint", self.otm_session.session_id)

    def connection_made(self, transport):
        self.transport = transport


class OTMBytesScheduler:
    scheduled_sessions = {}
    completed_sessions = []

    @classmethod
    def schedule_request(cls, request:WireData):
        ...


class OTMBytesMediator:
    ...
