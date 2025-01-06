"""
All the stuff related to kademlia goes here
"""
import asyncio
from typing import override

import kademlia.node
from kademlia import crawling, network, node, protocol, routing
from kademlia.crawling import NodeSpiderCrawl
from kademlia.protocol import log
from rpcudp.protocol import RPCProtocol

from src.avails import RemotePeer, const, use
from src.avails.bases import BaseDispatcher
from src.avails.events import RequestEvent
from src.core import Dock, get_this_remote_peer, peers
from src.core.peers import Storage
from src.core.transfers import REQUESTS_HEADERS
from src.core.transfers.transports import KademliaTransport


class RPCFindResponse(crawling.RPCFindResponse):
    @override
    def get_node_list(self):
        """
        Get the node list in the response.  If there's no value, this should
        be set.
        """
        nodelist = self.response[1] or []
        return [RemotePeer(*nodeple) for nodeple in nodelist]


class RPCCaller(RPCProtocol):
    __slots__ = ()

    async def call_find_node(self, node_to_ask, node_to_find):
        # address = (node_to_ask.ip, node_to_ask.port)
        result = await self.find_node(node_to_ask.req_uri, self.source_node.serialized,
                                      node_to_find.id)
        return self.handle_call_response(result, node_to_ask)

    async def call_find_value(self, node_to_ask, node_to_find):
        # address = (node_to_ask.ip, node_to_ask.port)
        result = await self.find_value(node_to_ask.req_uri, self.source_node.serialized,
                                       node_to_find.id)
        return self.handle_call_response(result, node_to_ask)

    async def call_ping(self, node_to_ask):
        # address = (node_to_ask.ip, node_to_ask.port)
        result = await self.ping(node_to_ask.req_uri, self.source_node.serialized)
        return self.handle_call_response(result, node_to_ask)

    async def call_store(self, node_to_ask, key, value):
        # address = (node_to_ask.ip, node_to_ask.port)
        result = await self.store(node_to_ask.req_uri, self.source_node.serialized, key, value)
        return self.handle_call_response(result, node_to_ask)

    async def call_store_peers_in_list(self, peer_to_ask, list_key, peer_list):
        if isinstance(list_key, (RemotePeer, node.Node)):
            list_key = list_key.id
        address = peer_to_ask.req_uri
        result = await self.store_peers_in_list(address, self.source_node.serialized, list_key, peer_list)
        return self.handle_call_response(result, peer_to_ask)

    async def call_find_peer_list(self, peer_to_ask, node_to_find):
        address = peer_to_ask.req_uri
        result = await self.find_list_of_peers(address, self.source_node.serialized, node_to_find.id)
        return self.handle_call_response(result, peer_to_ask)

    async def call_search_peers(self, peer_to_ask: RemotePeer, search_string):
        # address = peer_to_ask.network_uri
        result = await self.search_peers(peer_to_ask.req_uri, self.source_node.serialized, search_string)
        self.handle_call_response(result, peer_to_ask)
        return list(map(RemotePeer.load_from, result[1]))


class RPCReceiver(RPCProtocol):
    __slots__ = ()

    def rpc_ping(self, sender, sender_peer):
        self._check_in(sender_peer)
        return self.source_node.serialized

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


class KadProtocol(RPCCaller, RPCReceiver, protocol.KademliaProtocol):
    def __init__(self, source_node, storage, ksize):
        super().__init__(source_node, storage, ksize)
        self.router = AnotherRoutingTable(self, ksize, source_node)
        self.storage = storage

    def _check_in(self, peer):
        s = RemotePeer.load_from(peer)
        self.welcome_if_new(s)
        return s

    def _send_peer_lists(self, peer):
        for list_key, peer_list in self.storage.all_peers_in_lists():
            peer_list = list(peer_list)
            key_node = RemotePeer(list_key)
            neighbors = self.router.find_neighbors(key_node)
            if neighbors:
                last = neighbors[-1].distance_to(key_node)
                new_node_close = peer.distance_to(key_node) < last
                first = neighbors[0].distance_to(key_node)
                this_closest = self.source_node.distance_to(key_node) < first
            if not neighbors or (new_node_close and this_closest):  # noqa
                for i in peer_list:
                    asyncio.create_task(self.call_store_peers_in_list(peer, list_key, [i, ]))

    @override
    def welcome_if_new(self, peer):
        if self.router.is_new_node(peer):
            self._send_peer_lists(peer)
        super().welcome_if_new(peer)


class AnotherRoutingTable(routing.RoutingTable):
    @override
    def add_contact(self, peer: RemotePeer):
        super().add_contact(peer)
        Dock.peer_list.add_peer(peer)

    @override
    def remove_contact(self, peer: RemotePeer):
        super().remove_contact(peer)
        Dock.peer_list.remove_peer(peer.peer_id)


class PeerServer(network.Server):
    protocol_class = KadProtocol

    def __init__(self, ksize=20, alpha=3, node=None, storage=None):
        super().__init__(ksize, alpha, node, storage)
        self.add_this_peer_future = None
        self._transport = None

    @override
    async def bootstrap_node(self, addr):
        result = await self.protocol.ping(addr, bytes(self.node))
        return RemotePeer.load_from(result[1]) if result[0] else None

    def start(self):
        self.protocol = self._create_protocol()
        self.refresh_table()

    async def get_list_of_nodes(self, list_key):
        node = RemotePeer(list_key)
        nearest = self.protocol.router.find_neighbors(node)
        if not nearest:
            log.warning("There are no known neighbors to get key %s", list_key)
            return None
        peer_list_getter = peers.PeerListGetter(self.protocol, node, nearest,
                                                self.ksize, self.alpha)
        results = await peer_list_getter.find()
        if results is None:
            return results
        return [RemotePeer.load_from(peer) for peer_list in results for peer in peer_list]

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
        if await self.store_nodes_in_list(closest_list_id, [self.node, ]):
            log.debug(f'added this peer object in list_id={closest_list_id}')  # debug

        else:
            log.error("failed adding this peer object to lists")
            await asyncio.sleep(const.PERIODIC_TIMEOUT_TO_ADD_THIS_REMOTE_PEER_TO_LISTS)
            f = use.wrap_with_tryexcept(self.add_this_peer_to_lists)
            self.add_this_peer_future = asyncio.create_task(f())
            log.debug("scheduled callback to add this object to lists")

    async def store_nodes_in_list(self, list_key_id, peer_objs):
        list_key = RemotePeer(list_key_id)
        peer_objs = [bytes(x) for x in peer_objs]

        nearest = self.protocol.router.find_neighbors(list_key)
        if not nearest:
            log.info("There are no known neighbors to set key %s",
                     list_key_id.hex())
            return False
        spider = crawling.NodeSpiderCrawl(self.protocol, list_key, nearest,
                                          self.ksize, self.alpha)
        relevant_peers = await spider.find()

        # log.info("setting '%s' on %s", dkey.hex(), list(map(str, relevant_peers)))
        distances = [n.distance_to(list_key) for n in relevant_peers]
        if not distances:
            return False
        biggest = max(distances)
        if self.node.distance_to(list_key) < biggest:
            self.storage.store_peers_in_list(list_key.id, peer_objs)
        results = [self.protocol.call_store_peers_in_list(n, list_key, peer_objs) for n in relevant_peers]
        return any(await asyncio.gather(*results))

    async def get_remote_peer(self, peer_id):
        """
        Every call to this function not only gathers remote_peer object corresponding to peer_id
        but also updates `Dock.peer_list` cache, by reassigning all the peer objects that go through this network
        crawling process which helps in keeping cache upto date to some extent
        """
        node = RemotePeer(peer_id=peer_id)
        nodes = self.protocol.router.find_neighbors(node)

        spider = NodeSpiderCrawl(self.protocol, node, nodes,
                                 self.ksize, self.alpha)
        found_peers = await spider.find()
        for peer in found_peers:
            if peer.id == peer_id:
                return peer

    @property
    def transport(self):
        return self._transport

    @transport.setter
    def transport(self, transport):
        self._transport = transport
        if hasattr(self, 'protocol'):
            self.protocol.transport = transport


def _get_new_kademlia_server() -> PeerServer:
    s = PeerServer(storage=Storage())
    s.node = get_this_remote_peer()
    s.start()
    return s


def _register_into_dispatcher(server, dispatcher: BaseDispatcher):
    handler = KademliaHandler(server)
    event_header = REQUESTS_HEADERS.KADEMLIA
    dispatcher.register_handler(event_header, handler)


def prepare_kad_server(req_transport, dispatcher):
    kad_server = _get_new_kademlia_server()
    kad_server.transport = KademliaTransport(req_transport)
    _register_into_dispatcher(kad_server, dispatcher)
    return kad_server


def KademliaHandler(kad_server):
    def handle(event: RequestEvent):
        return kad_server.protocol.datagram_received(event.request['data'], event.from_addr)

    return handle


# monkey-patching to custom RPCFindResponse
crawling.RPCFindResponse = RPCFindResponse
network.Server.protocol_class = KadProtocol
kademlia.node.Node = RemotePeer
