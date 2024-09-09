import asyncio
import logging
from typing import override

import kademlia.node
import kademlia.protocol
from kademlia import crawling, network, routing

from src.avails import RemotePeer, use, const
from src.core import Dock, get_this_remote_peer, peers
from src.core.peers import Storage

log = logging.getLogger(__name__)


class RequestProtocol(kademlia.protocol.KademliaProtocol):
    def __init__(self, source_node, storage, ksize):
        super().__init__(source_node, storage, ksize)
        self.router = routing.RoutingTable(self, ksize, source_node)
        self.storage = storage
        self.source_node = source_node
        self.source_node_serialized = bytes(source_node)

    def _check_in(self, peer):
        s = RemotePeer.load_from(peer)
        self.welcome_if_new(s)
        return s

    def rpc_ping(self, sender, sender_peer):
        self._check_in(sender_peer)
        return self.source_node.id

    def rpc_store(self, sender, sender_peer, key, value):
        source = self._check_in(sender_peer)
        log.debug("got a store request from %s, storing '%s'='%s'",
                  sender, key.hex(), value)
        self.storage[key] = value
        return True

    def rpc_find_node(self, sender, sender_peer, key):
        source = self._check_in(sender_peer)
        log.info("finding neighbors of %i in local table",
                 source.long_id)
        node = RemotePeer(key)
        neighbors = self.router.find_neighbors(node, exclude=source)
        return list(map(tuple, neighbors))

    def rpc_find_value(self, sender, sender_peer, key):
        # source = self._check_in(sender_peer)
        self._check_in(sender_peer)
        value = self.storage.get(key, None)
        if value is None:
            return self.rpc_find_node(sender, sender_peer, key)
        return {'value': value}

    def rpc_find_list_of_peers(self, sender, sender_peer, list_key):
        # caller_peer = self._check_in(sender_peer)
        self._check_in(sender_peer)
        value = self.storage.get_list_of_peers(list_key)
        if value is None:
            return self.rpc_find_node(sender, sender_peer, list_key)
        return {'value': value}

    def rpc_store_peers_in_list(self, sender, caller_peer, list_key, peer_list):
        # caller_peer = RemotePeer.load_from(caller_peer)
        self._check_in(caller_peer)
        return self.storage.store_peers_in_list(list_key, peer_list)

    def rpc_search_peers(self, sender, caller_peer, search_string):
        self._check_in(caller_peer)
        relevant_peers = use.search_relevant_peers(Dock.peer_list, search_string)
        return list(map(bytes, relevant_peers))

    async def call_find_node(self, node_to_ask, node_to_find):
        address = (node_to_ask.ip, node_to_ask.port)
        result = await self.find_node(address, self.source_node_serialized,
                                      node_to_find.id)
        return self.handle_call_response(result, node_to_ask)

    async def call_find_value(self, node_to_ask, node_to_find):
        address = (node_to_ask.ip, node_to_ask.port)
        result = await self.find_value(address, self.source_node_serialized,
                                       node_to_find.id)
        return self.handle_call_response(result, node_to_ask)

    async def call_ping(self, node_to_ask):
        address = (node_to_ask.ip, node_to_ask.port)
        result = await self.ping(address, self.source_node_serialized)
        return self.handle_call_response(result, node_to_ask)

    async def call_store(self, node_to_ask, key, value):
        address = (node_to_ask.ip, node_to_ask.port)
        result = await self.store(address, self.source_node_serialized, key, value)
        return self.handle_call_response(result, node_to_ask)

    async def call_store_peers_in_list(self, peer_to_ask, list_key, peer_list):
        if not isinstance(list_key, bytes):
            list_key = list_key.id
        address = peer_to_ask.network_uri
        result = await self.store_peers_in_list(address, self.source_node_serialized, list_key, peer_list)
        return self.handle_call_response(result, peer_to_ask)

    async def call_find_peer_list(self, peer_to_ask, node_to_find):
        address = peer_to_ask.network_uri
        result = await self.find_list_of_peers(address, self.source_node_serialized, node_to_find.id)
        return self.handle_call_response(result, peer_to_ask)

    async def call_search_peers(self, peer_to_ask: RemotePeer, search_string):
        add0ress = peer_to_ask.network_uri
        result = await self.search_peers(add0ress, self.source_node_serialized, search_string)
        self.handle_call_response(result, peer_to_ask)
        return list(map(RemotePeer.load_from, result[1]))

    def _send_peer_lists(self, peer):
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

    @override
    def welcome_if_new(self, peer):
        super().welcome_if_new(peer)
        if not self.router.is_new_node(peer):
            return
        self._send_peer_lists(peer)
        self.router.add_contact(peer)
        Dock.peer_list.add_peer(peer)


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

    def _get_closest_list_id(self, node_list_ids: list[bytes]):
        nearest_list_id = 0
        prev_closest_xor = 2 ** 160
        for i in node_list_ids:
            current_xor = self.node.long_id ^ int(i.hex(), 16)
            if current_xor < prev_closest_xor:
                nearest_list_id = i
                prev_closest_xor = current_xor
        return nearest_list_id

    async def add_this_peer_to_lists(self):
        closest_list_id = self._get_closest_list_id(peers.node_list_ids)
        await self.store_nodes_in_list(closest_list_id, [self.node,])
        await asyncio.sleep(const.PERIODIC_TIMEOUT_TO_ADD_THIS_REMOTE_PEER_TO_LISTS)
        self.add_this_peer_future = asyncio.ensure_future(self.add_this_peer_to_lists())

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

        # log.info("setting '%s' on %s", dkey.hex(), list(map(str, relevant_peers)))
        biggest = max([n.distance_to(list_key) for n in relevant_peers])
        if self.node.distance_to(list_key) < biggest:
            self.storage.store_peers_in_list(list_key.id, peer_objs)
        results = [self.protocol.call_store_peers_in_list(n, list_key, peer_objs) for n in relevant_peers]
        return any(await asyncio.gather(*results))


network.Server.protocol_class = RequestProtocol
kademlia.node.Node = RemotePeer


def get_new_kademlia_server():
    _storage = Storage()
    s = PeerServer(storage=_storage)
    s.protocol_class = RequestProtocol
    s.node = get_this_remote_peer()
    return s
