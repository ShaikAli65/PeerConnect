
"""
Rumor-Mongering implementation of gossip protocol
"""
import asyncio
import random
import time

from src.avails import GossipMessage, Wire, WireData, connect, const
from src.core import Dock


class MessageItem:
    __slots__ = 'message_id', 'peer_list', 'time_in'
    __annotations__ = {
        'message_id': int,
        'peer_list': list[int],
        'time_in': float,
    }

    def __init__(self, message_id, time_in, peer_list):
        _l = list(peer_list)
        random.shuffle(_l)
        self.message_id = message_id
        self.peer_list = set(_l)
        self.time_in = time_in

    def __next__(self):
        return self.peer_list.pop()

    def __eq__(self, other):
        return self.message_id == other.message_id

    def __hash__(self):
        return self.message_id

    @property
    def id(self):
        return self.message_id


class MessageList:
    """"""
    def __init__(self, ttl):
        # tuple(timein, messageItem)
        self.message_list = {}
        self.ttl = ttl
        loop = asyncio.get_event_loop()
        self.dropped = set()
        self.message_remover = loop.call_later(self.ttl, self.__message_remover)

    def __message_remover(self):
        current_time = self._get_current_clock()
        for message_id in self.message_list:
            message_item = self.message_list[message_id]
            if current_time - message_item.time_in >= self.ttl:
                self.message_list.pop(message_id)
                self.dropped.add(message_id)
        loop = asyncio.get_event_loop()
        self.message_remover = loop.call_later(self.ttl, self.__message_remover)

    @staticmethod
    def _get_current_clock():
        return time.monotonic()

    @staticmethod
    def _get_list_of_peers():
        return list(Dock.peer_list)

    def push(self, message):
        peer_list = self._get_list_of_peers()
        message_item = MessageItem(message.id, self._get_current_clock(), peer_list)
        self.message_list[message.id] = message_item

    def __contains__(self, item):
        return item in self.message_list

    def get_random_peer_to_send_message(self, message_id):
        message_item = self.message_list[message_id]
        message_item.time_in = self._get_current_clock()
        return next(message_item)


class RumorMongerProtocol:
    messages = MessageList(const.MAX_TTL_FOR_GOSSIP)
    alpha = 2  # no.of nodes to forward a gossip at once

    @classmethod
    def message_arrived(cls, data:WireData):
        if data.id in cls.messages.dropped:
            return
        if data.id in cls.messages:
            for _ in range(cls.alpha):
                peer_id = cls.messages.get_random_peer_to_send_message(data.id)
                cls.forward_payload(data, peer_id)
            return
        cls.messages.push(data)
        return cls.message_arrived(data)

    @classmethod
    def gossip_message(cls, message: GossipMessage):
        cls.messages.push(message)
        for _ in range(cls.alpha):
            peer_id = cls.messages.get_random_peer_to_send_message(message.id)
            cls.forward_payload(message, peer_id)

    @staticmethod
    def forward_payload(message, peer_id):
        peer_obj = Dock.peer_list.get_peer(peer_id)
        sock = connect.UDPProtocol.create_sync_sock(const.IP_VERSION)
        return Wire.send_datagram(sock, peer_obj.req_uri, bytes(message))


def get_gossip():
    return RumorMongerProtocol


def join_gossip(kademlia_server):
    pass
