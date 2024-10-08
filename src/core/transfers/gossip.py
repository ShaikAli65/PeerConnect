import asyncio
import math
import random
import socket
import time
from collections import defaultdict
from dataclasses import dataclass
from itertools import count
from uuid import uuid4

from src.avails import (
    GossipMessage,
    PalmTreeInformResponse,
    RemotePeer,
    RumorMessageItem,
    Wire,
    WireData,
    connect,
    const,
    wire,
    use,
)

from src.avails.connect import UDPProtocol, get_free_port
from src.core import Dock, get_this_remote_peer
from src.core.transfers import HEADERS


class RumorMessageList:
    old_message_time_limit = 2

    def __init__(self, ttl):
        # tuple(timein, messageItem)
        self.message_list = {}
        self.ttl = ttl
        loop = asyncio.get_event_loop()
        self.dropped = set()
        self.message_remover = loop.call_later(self.ttl, self._disseminate)

    def _disseminate(self):
        current_time = self._get_current_clock()
        current_message_ids = self.message_list.keys()
        # :warning: make sure to create a copy of keys before iteration
        # if there is any possiblity of context change
        for message_id in current_message_ids:
            message_item = self.message_list[message_id]
            if self._is_old_enough(current_time, message_item.time_in):
                self.message_list.pop(message_id)
                self.dropped.add(message_id)
        loop = asyncio.get_event_loop()
        self.message_remover = loop.call_later(self.ttl / 2, self._disseminate)

    @classmethod
    def _is_old_enough(cls, current_time, message_time_in):
        return current_time - message_time_in > cls.old_message_time_limit

    @staticmethod
    def _get_current_clock():
        return time.monotonic()

    @staticmethod
    def _get_list_of_peers():
        return set(Dock.peer_list.keys())

    def push(self, message: GossipMessage):
        message_item = RumorMessageItem(
            message.id,
            self._get_current_clock(),
            message.created,
            set()
        )
        self.message_list[message.id] = message_item

    def _calculate_gossip_probability(self, message):
        # Implement Probabilistic Gossiping formula
        elapsed_time = time.monotonic() - message.created
        gossip_probability = 1 / (1 + elapsed_time / self.ttl)
        return gossip_probability

    def remove_message(self, message_id):
        self.message_list.pop(message_id)
        self.dropped.add(message_id)

    def __contains__(self, item):
        return item in self.message_list

    def sample_peers(self, message_id, sample_size):
        # using reserviour sampling algorithm
        # :todo: try working with bloom filters
        _m: RumorMessageItem = self.message_list[message_id]
        peer_list = self._get_list_of_peers() - _m.peer_list
        reservoir = []
        for i, peer_id in enumerate(peer_list):
            if i < sample_size:
                reservoir.append(peer_id)
            else:
                j = random.randint(0, i)
                if j < sample_size:
                    reservoir[j] = peer_id
        _m.peer_list |= set(reservoir)
        return reservoir


class RumorMongerProtocol:
    """
    Rumor-Mongering implementation of gossip protocol
    """
    alpha = 4  # no.of nodes to forward a gossip at once

    def __init__(self):
        self.messages = RumorMessageList(const.NODE_POV_GOSSIP_TTL)
        self.send_sock = None
        self.global_gossip_ttl = const.GLOBAL_TTL_FOR_GOSSIP

    def initiate(self):
        self.send_sock = UDPProtocol.create_sync_sock(const.IP_VERSION)

    def message_arrived(self, data: GossipMessage):
        print("got a message to gossip", data)
        if not self.should_gossip(data):
            return
        print("gossiping message to", end=" ")
        if data.id in self.messages:
            sampled_peers = self.messages.sample_peers(data.id, self.alpha)
            for peer_id in sampled_peers:
                p = self.forward_payload(data, peer_id)
                print(p, end=", ")
            return
        print('')
        self.gossip_message(data)
        print("Gossip message received and processed: %s" % data)

    def should_gossip(self, message):
        if message.id in self.messages.dropped:
            print("not gossiping due to message id found in dropped", message.id)
            return False
        elapsed_time = time.time() - message.created
        if elapsed_time > self.global_gossip_ttl:
            print("not gossiping, global timeout reached", elapsed_time)
            return False
        # Decrease gossip chance based on time
        gossip_chance = max(0.6, (self.global_gossip_ttl - elapsed_time) / self.global_gossip_ttl)
        # Minimum 60% chance
        if not (w := random.random() < gossip_chance):
            print("not gossiping probability check failed")
        return w

    def gossip_message(self, message: GossipMessage):
        print("gossiping new message", message, "to", end="")
        self.messages.push(message)
        sampled_peers = self.messages.sample_peers(message.id, self.alpha)
        for peer_id in sampled_peers:
            p = self.forward_payload(message, peer_id)
            print(p, end=", ")
        print("")

    def forward_payload(self, message, peer_id):
        peer_obj = Dock.peer_list.get_peer(peer_id)
        if peer_obj is not None:
            return Wire.send_datagram(self.send_sock, peer_obj.req_uri, bytes(message))
        return peer_obj


class PalmTreeProtocol:
    request_timeout = 3

    def __init__(self, center_peer: RemotePeer, max_forwards, session_id, session_key, peers: list[RemotePeer]):
        """
        !! do not include center_peer in peers list passed in
        """
        self.peer_list = peers
        self.center_peer = center_peer
        self.adjacency_list: dict[str: list[RemotePeer]] = defaultdict(list)
        self.dimensions = (2 ** math.ceil(math.log2(len(peers)))).bit_length() - 1
        self.confirmed_peers: dict[str, PalmTreeInformResponse] = {}
        self.max_forwards = max_forwards
        self.create_hypercube()
        self.session = PalmTreeSession(
            center_peer.id,
            self.adjacency_list[center_peer.id],
            session_key,
            session_id,
            self.max_forwards,
            self.request_timeout,
        )

        addr = (get_this_remote_peer().ip, get_free_port())
        loop = asyncio.get_event_loop()
        passive_server_sock = UDPProtocol.create_async_server_sock(loop, addr, family=const.IP_VERSION)
        self.mediator = PalmTreeMediator(
            self.session,
            passive_server_sock,
            get_this_remote_peer().uri
        )

    def create_hypercube(self):
        """Create the hypercube topology of peers"""
        peer_id_to_peer_mapping = {i: peer for i, peer in enumerate(self.peer_list + [self.center_peer])}
        # imagine writing :: zip(range(len(self.peer_list)), self.peer_list)
        for i in range(len(self.peer_list)):
            for j in range(self.dimensions):
                neighbor = i ^ (1 << j)
                if neighbor < len(self.peer_list):
                    peer = peer_id_to_peer_mapping[j]
                    neigh = peer_id_to_peer_mapping[neighbor]
                    self.adjacency_list[peer.id].append(neigh.id)

    async def start(self):
        """Start the process of sending data to peers."""
        await self.inform_peers()
        self.update_states()
        await self.trigger_spanning_formation()

    async def inform_peers(self):
        self.confirmed_peers[self.center_peer.id] = PalmTreeInformResponse(
            get_this_remote_peer().id,
            self.mediator.passive_server_sock.getsockname(),
            self.mediator.active_endpoint_addr,
            self.session.key,
        )
        trigger_request = bytes(
            WireData(
                header=HEADERS.GOSSIP_CREATE_SESSION,
                _id=get_this_remote_peer().id,
                session_id=self.session.id,
                session_key=self.session.key,
                max_forwards=self.max_forwards,
                adjacent_peers=None,
            )
        )
        req_tasks = [self.trigger_schedular_of_peer(trigger_request, peer) for peer in self.peer_list]
        for f in asyncio.as_completed(req_tasks):
            r = await f
            if r[0]:
                reply_data = r[1]
                self.confirmed_peers[reply_data.peer_id] = reply_data
            else:
                discard_peer = r[1].id
                for peer_id in self.adjacency_list[discard_peer]:
                    self.adjacency_list[peer_id].remove(discard_peer)
                del self.adjacency_list[discard_peer]
        # send an audit event to page confirming peers

    async def trigger_schedular_of_peer(self, trigger_request: bytes, peer: RemotePeer) -> tuple[bool, RemotePeer | PalmTreeInformResponse]:
        loop = asyncio.get_event_loop()
        connection = await UDPProtocol.create_connection_async(loop, peer.req_uri, self.request_timeout)
        with connection:
            Wire.send_datagram(connection, peer.req_uri, trigger_request)
            try:
                data, addr = await asyncio.wait_for(Wire.recv_datagram_async(connection), self.request_timeout)
            except asyncio.TimeoutError:
                return False, peer
            reply_data = PalmTreeInformResponse.load_from(data)
            return True, reply_data

    def update_states(self):
        self.__update_internal_mediator_state()
        states_data = WireData(
            header=HEADERS.GOSSIP_SESSION_STATE_UPDATE,
            addresses_mapping=None,
        )
        s = self.mediator.passive_server_sock
        for peer_id, response_data in self.confirmed_peers.items():
            peer_ids = self.adjacency_list[peer_id]
            peer_responses = [self.confirmed_peers.get(p_id) for p_id in peer_ids]

            states_data['addresses_mapping'] = [
                (p_id, peer_response.passive_addr, peer_response.active_addr)
                for p_id, peer_response in zip(peer_ids, peer_responses) if peer_response
            ]

            Wire.send_datagram(s, response_data.passive_addr, bytes(states_data))

    def __update_internal_mediator_state(self):
        self.mediator.gossip_update_state(
            WireData(
                header=HEADERS.GOSSIP_SESSION_STATE_UPDATE,
                addresses_mapping=(
                    (peer_id, peer_response.passive_addr, peer_response.active_addr) for peer_id, peer_response in
                    zip(
                        self.adjacency_list[self.center_peer.id],
                        map(
                            lambda x: self.confirmed_peers.get(x),
                            self.adjacency_list[self.center_peer.id]
                        )
                    )
                    if peer_response
                )  # keeping this as a generator because it's gonna
                #    directly iterated over in the undelying function
            )
        )

    async def trigger_spanning_formation(self):
        tree_check_message_id = uuid4().int
        spanning_trigger_header = WireData(
                header=HEADERS.GOSSIP_TREE_CHECK,
                _id=get_this_remote_peer().id,
                message_id=tree_check_message_id,
                session_id=self.session.id,
            )
        # initial_peers = self.adjacency_list[self.center_peer]
        # if not initial_peers:
        #     # :todo: handle the case where all the peers adjacent to center peer went offline
        #     pass
        self.mediator.gossip_tree_check(spanning_trigger_header, self.mediator.passive_server_sock.getsockname())


@dataclass(slots=True)
class PalmTreeSession:
    """
    Args:
        `originater_id(str)`: the one who initiated this session
        `adjacent_peers(list[str])` : all the peers to whom we should be in contact
        `session_key(str)` : session key used to encrypt data
        `session_id(int)` : self-explanatory
        `max_forwards`(int) : maximum number of resends this instance should perform for every packet received
        `link_wait`(double) : timeout for any i/o operations
    """
    originater_id: str
    adjacent_peers: list[str]
    id: int
    key: str
    max_forwards: int
    link_wait: int


class PalmTreeLink:
    PASSIVE = 0x00
    ACTIVE = 0x01
    ONLINE = 0x01
    OFFLINE = 0x00

    id_factory = count()

    def __init__(self, a, b, peer_id, connection: connect.Socket = None, link_type: int = PASSIVE):
        """
        Arguments:
            a = address of left end of this link
            b = address of right end of this link
            peer_id = id of peer on the other side
            connection = a passive socket used to communicate between both ends
            link_type = ACTIVE (stream socket) or PASSIVE (datagram socket)
        """
        self.type = link_type
        self.left = a
        self.right = b
        self.connection = connection
        self.peer_id = peer_id
        self.id = next(self.id_factory)
        self.status = self.OFFLINE

    async def send_active_message(self, message: bytes):
        await Wire.send_async(sock=self.connection, data=message)

    async def send_passive_message(self, message: bytes):
        Wire.send_datagram(self.connection, self.right, message)

    @property
    def is_passive(self):
        return self.type == self.PASSIVE

    @property
    def is_active(self):
        return self.type == self.ACTIVE

    @property
    def is_online(self):
        return self.status == self.ONLINE

    def clear(self):
        self.status = PalmTreeLink.OFFLINE
        self.connection.close()
        self.connection = None

    def __eq__(self, other):
        return other.id == self.id and self.right == other.right

    def __hash__(self):
        return hash(self.id) ^ hash(self.right) ^ hash(self.left)


class PalmTreeMediator(asyncio.DatagramProtocol):
    def __init__(self, session, passive_server_sock=None, active_endpoint_addr=None):
        self.session: PalmTreeSession = session
        self.all_tasks = []
        self.passive_server_sock: connect.Socket | socket.socket = passive_server_sock
        self.active_endpoint_addr: tuple[str, int] = active_endpoint_addr
        self.all_links: dict[str, tuple[PalmTreeLink, PalmTreeLink]] = {}
        self.active_links: dict[str, PalmTreeLink] = {}
        self.passive_links: dict[str, PalmTreeLink] = {}

    def start_session(self):
        f = use.wrap_with_tryexcept(self.session_init)
        self.session_task = asyncio.create_task(f)

    async def session_init(self):
        loop = asyncio.get_event_loop()
        if self.passive_server_sock:
            func = loop.create_datagram_endpoint(
                lambda: self,
                sock=self.passive_server_sock,
            )
        else:
            func = loop.create_datagram_endpoint(
                lambda: self,
                (get_this_remote_peer().ip, get_free_port()),
                family=const.IP_VERSION,
            )
        self.transport, self.session_protocol = await func
        self.passive_server_sock = self.transport.get_extra_info('socket')

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        #
        #  WARNING: only use self.transport to perform any i/o operations
        #  self.passive_server_sock can be socket.socket or connect.Socket
        #  depends on whether this object creator is the actual sender or else
        #
        unpacked_data = wire.unpack_datagram(data)
        if unpacked_data is None:
            return
        print(f"[{self.session}] got some data at passive endpoint", unpacked_data)
        if unpacked_data.header in self.__dict__.keys():
            getattr(self, unpacked_data.header)(unpacked_data, addr)

    def gossip_update_state(self, state_data: WireData, addr=None):
        addresses = state_data['addresses_mapping']
        this_passive_address = self.passive_server_sock.getsockname()
        this_active_address = self.active_endpoint_addr
        for peer_id, passive_addr, active_addr in addresses:
            active_link = PalmTreeLink(this_active_address, active_addr, peer_id, link_type=PalmTreeLink.ACTIVE)
            passive_link = PalmTreeLink(
                this_passive_address,
                passive_addr,
                peer_id,
                self.passive_server_sock,
                link_type=PalmTreeLink.PASSIVE
            )
            passive_link.status = PalmTreeLink.ONLINE
            self.all_links[peer_id] = (passive_link, active_link)
        self.session.max_forwards = min(len(self.all_links), self.session.max_forwards)

    def add_stream_link(self, data: WireData, connection):
        peer_id = data.id
        if peer_id in self.active_links:
            self.active_links[peer_id].connection = connection
        # stream connections are assumed to be active connections for now

    def gossip_tree_check(self, tree_check_packet: WireData, addr):
        this_peer_id = get_this_remote_peer().id
        gossip_link_reject_message = WireData(
            header=HEADERS.GOSSIP_DOWNGRADE_CONN,
            _id=this_peer_id,
        )
        if len(self.active_links) > self.session.max_forwards:
            self.transport.sendto(bytes(gossip_link_reject_message), addr)
            return

        sender_id = tree_check_packet.id
        if sender_id in self.all_links:
            upgrade_conn_packet = WireData(
                header=HEADERS.GOSSIP_UPGRADE_CONN,
                _id=this_peer_id,
            )
            self.active_links[sender_id] = self.all_links[sender_id][PalmTreeLink.ACTIVE]
            self.transport.sendto(bytes(upgrade_conn_packet), addr)

        tree_check_packet.id = this_peer_id
        sampled_peer_ids = random.sample(list(self.all_links), self.session.max_forwards)
        for peer_id in sampled_peer_ids:
            passive_link, active_link = self.all_links[peer_id]
            passive_link.send_passive_message(bytes(tree_check_packet))
            self.active_links[peer_id] = self.all_links[peer_id][PalmTreeLink.ACTIVE]

        self.passive_links.update(
            {
                peer_id: self.all_links[peer_id][PalmTreeLink.PASSIVE]
                for peer_id in set(self.all_links) - set(self.active_links)
            }
        )

    def gossip_downgrade_connection(self, data: WireData, addr:tuple[str, int]):
        peer_id = data.id
        if peer_id in self.active_links:
            a_link = self.active_links.pop(peer_id)
            a_link.clear()
            self.passive_links[peer_id] = self.all_links[peer_id][PalmTreeLink.PASSIVE]

    def gossip_upgrade_connection(self, data: WireData, addr:tuple[str, int]):
        peer_id = data.id
        if peer_id not in self.active_links:
            return
        link = self.active_links[peer_id]
        f = use.wrap_with_tryexcept(self.activate_link, link)
        asyncio.create_task(f)

    async def activate_link(self, link: PalmTreeLink):
        if link.is_online:
            return
        stream_sock = await connect.create_connection_async(link.right, self.session.link_wait)
        await Wire.send_async(
            stream_sock,
            bytes(
                WireData(
                    header=HEADERS.GOSSIP_UPDATE_STREAM_LINK,
                    _id=get_this_remote_peer().id,
                    session_id=self.session.id,
                )
            )
        )
