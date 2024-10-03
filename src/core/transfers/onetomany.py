import asyncio
from dataclasses import dataclass

from src.avails import RemotePeer, WireData, const, unpack_datagram
from .. import get_this_remote_peer


class SendOTMBytes:
    def __init__(self, data: bytes, peers: list[RemotePeer], session_id):
        self.data = data
        peers.append(get_this_remote_peer())
        self.peer_list = peers
        self.session_id = session_id
        self.confirmed_peers = None


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
