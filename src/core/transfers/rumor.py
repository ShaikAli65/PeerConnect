import asyncio
import random
import time

from src.avails import GossipMessage, RumorMessageItem, Wire, const
from src.core import Dock


class RumorMessageList:

    def __init__(self, ttl):
        # tuple(timein, messageItem)
        self.message_list = {}
        self.ttl = ttl
        self.dropped = set()
        # self._disseminate()

    def _disseminate(self):
        current_time = self._get_current_clock()
        current_message_ids = list(self.message_list.keys())
        # :warning: make sure to create a copy of keys before iteration
        # if there is any possiblity of context change
        for message_id in current_message_ids:
            message_item = self.message_list[message_id]
            if self._is_old_enough(current_time, message_item.time_in):
                self.message_list.pop(message_id)
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


class RumorPolicy:

    global_gossip_ttl = const.GLOBAL_TTL_FOR_GOSSIP
    min_chance = 0.6

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
    """

    alpha = 3
    policy_class = RumorPolicy

    def __init__(self, datagram_transport, message_list_class: type[RumorMessageList]):
        self.message_list = message_list_class(const.NODE_POV_GOSSIP_TTL)
        self.send_sock = datagram_transport
        self.policy = self.policy_class(self)
        self._is_initiated = True

    def message_arrived(self, data: GossipMessage):
        print("got a message to gossip", data)

        if not data.fields_check():
            print(f"fields missing, ignoring message: {data.actual_data}")
            return
        if not self.policy.should_rumor(data):
            return

        if data.id in self.message_list:
            # no need to re-enter message into list, this refreshes timer of that message
            print("gossip forwarding seen message")
            self._gossip_forward(message=data)
        else:
            self.gossip_message(data)

        print("Gossip message received and processed: %s" % data)

    def __forward_payload(self, message, peer_id):
        peer_obj = Dock.peer_list.get_peer(peer_id)
        if peer_obj is not None:
            Wire.send_datagram(self.send_sock, peer_obj.req_uri, bytes(message))
            return peer_obj

    def gossip_message(self, message):
        print("gossiping new message", message, "to")
        self.message_list.push(message)
        self._gossip_forward(message)

    def _gossip_forward(self, message: GossipMessage):
        sampled_peers = self.message_list.sample_peers(message.id, self.alpha)

        # debug
        if sampled_peers:
            print("gossiping message to")

        for peer_id in sampled_peers:
            p = self.__forward_payload(message, peer_id)
            print(p.req_uri)

    def __del__(self):
        self.send_sock.close()

    def __repr__(self):
        return str(f"<RumorMongerProtocol initiated={self._is_initiated}>")
