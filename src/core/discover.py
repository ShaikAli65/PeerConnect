import asyncio
import functools
from collections import defaultdict
from typing import override

import kademlia.node
import kademlia.protocol
from kademlia import network, storage, crawling

from src.avails import RemotePeer
from src.core import peers, get_this_remote_peer, Dock
from src.managers.statemanager import State


class RequestProtocol(kademlia.protocol.KademliaProtocol):
    def __init__(self, source_node, storage, ksize):
        super().__init__(source_node, storage, ksize)

    def rpc_find_list_of_peers(self, sender, caller_peer, list_key):
        caller_peer = RemotePeer(caller_peer, sender[0], sender[1])
        self.welcome_if_new(caller_peer)
        value = self.storage.get_list_of_peers(list_key)
        if value is None:
            return self.rpc_find_node(sender, caller_peer.id, list_key)
        return {'value': value}

    def rpc_store_peers_in_list(self, sender, caller_peer, list_key, peer_list):
        caller_peer = RemotePeer(caller_peer, sender[0], sender[1])
        self.welcome_if_new(caller_peer)
        return self.storage.store_peers_in_list(list_key, peer_list)

    def rpc_search_peers(self, sender, caller_peer, search_string):
        caller_peer = RemotePeer(caller_peer, sender[0], sender[1])
        self.welcome_if_new(caller_peer)
        relevant_peers = Dock.peer_list.search_relevant_peers(search_string)
        return list(map(bytes, relevant_peers))

    async def call_store_peers_in_list(self, peer_to_ask, list_key, peer_list):
        if not isinstance(list_key, bytes):
            list_key = list_key.id
        address = peer_to_ask.network_uri
        result = await self.store_peers_in_list(address, self.source_node.id, list_key, peer_list)
        return self.handle_call_response(result, peer_to_ask)

    async def call_find_peer_list(self, peer_to_ask, node_to_find):
        address = peer_to_ask.network_uri
        result = await self.find_list_of_peers(address, self.source_node.id, node_to_find.id)
        return self.handle_call_response(result, peer_to_ask)

    async def call_search_peers(self, peer_to_ask: RemotePeer, search_string):
        address = peer_to_ask.network_uri
        result = await self.search_peers(address, search_string)
        self.handle_call_response(result, peer_to_ask)
        return list(map(RemotePeer.load_from, result[1]))

    @override
    def welcome_if_new(self, peer):
        super().welcome_if_new(peer)
        if not self.router.is_new_node(peer):
            return
        for list_key, peer_list in self.storage.all_peers_in_lists():
            peer_list = list(peer_list)
            keynode = RemotePeer(list_key)
            neighbors = self.router.find_neighbors(keynode)
            if neighbors:
                last = neighbors[-1].distance_to(keynode)
                new_node_close = peer.distance_to(keynode) < last
                first = neighbors[0].distance_to(keynode)
                this_closest = self.source_node.distance_to(keynode) < first
            if not neighbors or (new_node_close and this_closest):  # noqa
                for i in peer_list:
                    asyncio.ensure_future(self.call_store_peers_in_list(peer, list_key, [i,]))
        self.router.add_contact(peer)


class PeerServer(network.Server):
    def __init__(self, ksize=20, alpha=3, node=None, storage=None):
        super().__init__(ksize, alpha, node, storage)
        self.add_this_peer_future = None

    async def get_list_of_nodes(self, list_key):
        # if this node has it, return it
        if self.storage.get_list_of_peers(list_key) is not None:
            return [RemotePeer.load_from(data) for data in self.storage.get_list_of_peers(list_key)]

        node = RemotePeer(list_key)
        nearest = self.protocol.router.find_neighbors(node)
        if not nearest:
            # log.warning("There are no known neighbors to get key %s", key)
            return None
        peer_list_getter = peers.PeerListGetter(self.protocol, node, nearest,
                                                self.ksize, self.alpha)
        results = await peer_list_getter.find()
        if results is None:
            return results

        return [RemotePeer.load_from(data) for data in results]

    def get_closest_list_id(self, node_list_ids:list[bytes]):
        nearest_list_id = 0
        prev_closest_xor = 2 ** 160
        for i in node_list_ids:
            current_xor = self.node.long_id ^ int(i.hex(), 16)
            if current_xor < prev_closest_xor:
                nearest_list_id = i
                prev_closest_xor = current_xor

        return nearest_list_id

    async def add_this_peer_to_lists(self, timeout=0.001):
        closest_list_id = self.get_closest_list_id(peers.node_list_ids)
        what = await self.store_nodes_in_list(closest_list_id, [self.node,])
        if what is False:
            # loop = asyncio.get_event_loop()
            print('what is False registering again')
            await asyncio.sleep(timeout)
            await Dock.state_handle.put_state(
                State(
                    'add_this_peer_to_lists',
                    functools.partial(self.add_this_peer_to_lists, timeout * 1.5),
                )
            )

    async def store_nodes_in_list(self, list_key_id, peer_objs):
        list_key = RemotePeer(list_key_id)
        peer_objs = [bytes(x) for x in peer_objs]

        nearest = self.protocol.router.find_neighbors(list_key)
        if not nearest:
            # log.warning("There are no known neighbors to set key %s",
            #             dkey.hex())
            return False
        spider = crawling.NodeSpiderCrawl(self.protocol, list_key, nearest,
                                          self.ksize, self.alpha)
        relevant_peers = await spider.find()
        peers.SearchCrawler.add_responsible_peers_for_peer_lists_to_cache(list_key_id, relevant_peers)

        # log.info("setting '%s' on %s", dkey.hex(), list(map(str, relevant_peers)))
        biggest = max([n.distance_to(list_key) for n in relevant_peers])
        if self.node.distance_to(list_key) < biggest:
            self.storage.store_peers_in_list(list_key.id, peer_objs)
        results = [self.protocol.call_store_peers_in_list(n, list_key, peer_objs) for n in relevant_peers]
        return any(await asyncio.gather(*results))


class Storage(storage.ForgetfulStorage):
    node_lists_ids = set(peers.node_list_ids)
    peer_data_storage = defaultdict(set)

    def get_list_of_peers(self, list_key):
        if list_key in self.peer_data_storage:
            return list(self.peer_data_storage.get(list_key))
        return None

    def all_peers_in_lists(self):
        return self.peer_data_storage.items()

    def store_peers_in_list(self, list_key, list_of_peers):
        if list_key in self.node_lists_ids:
            self.peer_data_storage[list_key] |= set(list_of_peers)
            Dock.peer_list.extend(map(RemotePeer.load_from, list_of_peers))
        return True


network.Server.protocol_class = RequestProtocol
kademlia.node.Node = RemotePeer


def get_new_kademlia_server():
    _storage = Storage()
    s = PeerServer(storage=_storage)
    s.protocol_class = RequestProtocol
    s.node = get_this_remote_peer()
    return s
