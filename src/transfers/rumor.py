import asyncio
import random
import time

from src.avails import GossipMessage, RumorMessageItem, RumorMessageList, RumorPolicy, const
from src.core.public import Dock
from src.transfers.transports import GossipTransport


class SimpleRumorMessageList(RumorMessageList):
    __slots__ = '_message_list', 'ttl', 'dropped'

    def __init__(self, ttl):
        self._message_list = {}
        self.ttl = ttl
        self.dropped = set()
        # self._disseminate()

    def _disseminate(self):
        current_time = self._get_current_clock()
        current_message_ids = list(self._message_list.keys())
        # :warning: make sure to create a copy of keys before iteration
        # if there is any possibility of context change

        for message_id in current_message_ids:
            message_item = self._message_list[message_id]
            if self._is_old_enough(current_time, message_item.time_in):
                self._message_list.pop(message_id)
                self.dropped.add(message_id)
        loop = asyncio.get_event_loop()
        self.message_remover = loop.call_later(self.ttl / 2, self._disseminate)  # noqa

    @classmethod
    def _is_old_enough(cls, current_time, message_time_in):
        return current_time - message_time_in > const.NODE_POV_GOSSIP_TTL

    @staticmethod
    def _get_current_clock():
        return time.monotonic()

    @staticmethod
    def _get_list_of_peers():
        return NotImplemented

    def push(self, message: GossipMessage):
        message_item = RumorMessageItem(
            message.id, self._get_current_clock(), message.created, set()
        )
        self._message_list[message.id] = message_item

    def _calculate_gossip_probability(self, message):
        # Implement Probabilistic Gossiping formula
        elapsed_time = time.monotonic() - message.created
        gossip_probability = 1 / (1 + elapsed_time / self.ttl)
        return gossip_probability

    def remove_message(self, message_id):
        self._message_list.pop(message_id)
        self.dropped.add(message_id)

    def __contains__(self, item):
        return item in self._message_list

    def sample_peers(self, message_id, sample_size):
        # using reservoir sampling algorithm
        # TODO: try working with bloom filters
        _m: RumorMessageItem = self._message_list[message_id]
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


class DefaultRumorPolicy(RumorPolicy):
    global_gossip_ttl = const.GLOBAL_TTL_FOR_GOSSIP
    min_chance = 0.6

    __slots__ = 'protocol_class',

    def __init__(self, protocol_class):
        self.protocol_class = protocol_class

    def should_rumor(self, message: GossipMessage):
        if message.id in self.protocol_class.message_list.dropped:
            print("not gossiping due to message id found in dropped", message.id)
            return False
        elapsed_time = time.time() - message.created
        if elapsed_time > self.global_gossip_ttl:
            print("not gossiping, global timeout reached", elapsed_time)
            return False
        # Decrease gossip chance based on time
        gossip_chance = max(
            self.min_chance,
            (self.global_gossip_ttl - elapsed_time) / self.global_gossip_ttl,
        )
        # Minimum 60% chance
        if not (w := random.random() < gossip_chance):
            print("not gossiping probability check failed")
        return w


class RumorMongerProtocol:
    """
    Rumor-Mongering implementation of gossip protocol
    Once a message is created then it is not subject to any change at any peer
    """

    alpha = 3
    policy_class: RumorPolicy = DefaultRumorPolicy

    def __init__(self, datagram_transport: GossipTransport, message_list_class: type[SimpleRumorMessageList]):
        self.message_list = message_list_class(const.NODE_POV_GOSSIP_TTL)
        self.transport = datagram_transport
        self.policy = self.policy_class(self)
        self._is_initiated = True

    def message_arrived(self, data: GossipMessage, from_addr):

        if not data.fields_check():
            print(f"fields missing, ignoring message: {data.actual_data}")
            return

        if not self.policy.should_rumor(data):
            return

        if data.id in self.message_list:
            # no need to re-enter message into list, this refreshes timer of that message
            print("[GOSSIP] forwarding seen message")
            self._gossip_forward(message=data)
        else:
            self.gossip_message(data)

        print("[GOSSIP] message received and processed: %s" % data)

    def __forward_payload(self, message, peer_id):
        peer_obj = Dock.peer_list.get_peer(peer_id)
        if peer_obj is not None:
            self.transport.sendto(bytes(message), peer_obj.req_uri)
            return peer_obj

    def gossip_message(self, message):
        print("[GOSSIP] gossiping new message", message, "to")
        self.message_list.push(message)
        self._gossip_forward(message)

    def _gossip_forward(self, message: GossipMessage):
        sampled_peers = self.message_list.sample_peers(message.id, self.alpha)

        if sampled_peers:
            print("gossiping message to")  # debug

        for peer_id in sampled_peers:
            p = self.__forward_payload(message, peer_id)
            print(p.req_uri)

    def is_seen(self, message: GossipMessage):
        return message.id in self.message_list

    def __del__(self):
        self.transport.close()

    def __repr__(self):
        return str(f"<RumorMongerProtocol initiated={self._is_initiated}>")
