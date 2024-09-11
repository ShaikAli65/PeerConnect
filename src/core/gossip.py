
"""
Rumor-Mongering implementation of gossip protocol
"""
import asyncio
import random
import time

from src.avails import GossipMessage, Wire, connect, const
from src.core import Dock


class MessageItem:
    __slots__ = 'message_id', 'peer_list', 'time_in', 'creation_time'
    __annotations__ = {
        'message_id': int,
        'peer_list': list[int],
        'time_in': float,
        'creation_time': float,
    }

    def __init__(self, message_id, time_in, creation_time, peer_list):
        self.message_id = message_id
        self.peer_list = set(peer_list)
        self.time_in = time_in
        self.creation_time = creation_time

    def __next__(self):
        return self.peer_list.pop()

    def __eq__(self, other):
        return self.message_id == other.message_id

    def __hash__(self):
        return self.message_id

    def __lt__(self, other):
        return self.time_in < other.time_in

    @property
    def id(self):
        return self.message_id


class MessageList:
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
        for message_id in self.message_list:
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
        return set(Dock.peer_list)

    def push(self, message: GossipMessage):
        message_item = MessageItem(
            message.id,
            self._get_current_clock(),
            message.created,
            []
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
        _m:MessageItem = self.message_list[message_id]
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
    messages = MessageList(const.NODE_POV_GOSSIP_TTL)
    alpha = 4  # no.of nodes to forward a gossip at once
    send_sock = None
    global_gossip_ttl = const.GLOBAL_TTL_FOR_GOSSIP

    @classmethod
    def initiate(cls):  
        cls.send_sock = connect.UDPProtocol.create_sync_sock(const.IP_VERSION)

    @classmethod
    def message_arrived(cls, data: GossipMessage):
        if not cls.should_gossip(data):
            return
        if data.id in cls.messages:
            sampled_peers = cls.messages.sample_peers(data.id, cls.alpha)
            for peer_id in sampled_peers:
                cls.forward_payload(data, peer_id)
            return
        cls.messages.push(data)
        return cls.message_arrived(data)

    @classmethod
    def should_gossip(cls, message):
        if message.id in cls.messages.dropped:
            return False
        elapsed_time = time.monotonic() - message.created
        if elapsed_time > cls.global_gossip_ttl:
            return False
        # Decrease gossip chance based on time
        gossip_chance = max(0.4, (cls.global_gossip_ttl - elapsed_time) / cls.global_gossip_ttl)
        # Minimum 40% chance
        return random.random() < gossip_chance

    @classmethod
    def gossip_message(cls, message: GossipMessage):
        cls.messages.push(message)
        sampled_peers = cls.messages.sample_peers(message.id, cls.alpha)
        for peer_id in sampled_peers:
            cls.forward_payload(message, peer_id)

    @classmethod
    def forward_payload(cls, message, peer_id):
        peer_obj = Dock.peer_list.get_peer(peer_id)
        if peer_obj is not None:
            return Wire.send_datagram(cls.send_sock, peer_obj.req_uri, bytes(message))


def get_gossip():
    return RumorMongerProtocol


def join_gossip(kademlia_server):
    pass
