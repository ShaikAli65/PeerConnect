from collections import defaultdict

from typing import override

from kademlia import crawling, storage

from src.avails import RemotePeer, use
from src.core import Dock

node_list_ids = [
    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
    b'\x0c\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc',
    b'\x19\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x98',
    b'&ffffffffffffffffffd',
    b'33333333333333333330',
    b'?\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfc',
    b'L\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xc8',
    b'Y\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x94',
    b'fffffffffffffffffff`',
    b's333333333333333333,',
    b'\x7f\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xf8',
    b'\x8c\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xc4',
    b'\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x90',
    b'\xa6ffffffffffffffffff\\',
    b'\xb3333333333333333333(',
    b'\xbf\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xf4',
    b'\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xcc\xc0',
    b'\xd9\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x99\x8c',
    b'\xe6ffffffffffffffffffX',
    b'\xf3333333333333333333$',
]


class PeerListGetter(crawling.ValueSpiderCrawl):
    initial_list = Dock.peer_list
    previously_fetched_index = 0
    node_list_ids = node_list_ids

    async def find(self):
        return await self._find(self.protocol.call_find_peer_list)

    @override
    async def _handle_found_values(self, values):
        peer = self.nearest_without_value.popleft()
        if peer:
            await self.protocol.call_store_peers_in_list(peer, self.node.id, values)
        return values

    @classmethod
    async def get_more_peers(cls, peer_server) -> list[RemotePeer]:
        print("previous index", cls.previously_fetched_index)
        if cls.previously_fetched_index >= len(cls.node_list_ids) - 1:
            cls.previously_fetched_index = 0

        find_list_id = cls.node_list_ids[cls.previously_fetched_index]
        print("looking into", find_list_id)
        list_of_peers = await peer_server.get_list_of_nodes(find_list_id)
        cls.previously_fetched_index += 1

        if list_of_peers:
            cls.initial_list.extend(list_of_peers)

            return list_of_peers

        return []


class SearchCrawler:
    node_list_ids = node_list_ids
    list_id_mapper_handle = None

    @classmethod
    async def get_relevant_peers_for_list_id(cls, node_server, list_id):
        peer = RemotePeer(list_id)
        nearest = node_server.protocol.router.find_neighbors(peer)
        crawler = crawling.NodeSpiderCrawl(
            node_server.protocol,
            peer,
            nearest,
            node_server.ksize,
            node_server.alpha
        )
        responsible_nodes = await crawler.find()
        return responsible_nodes

    @classmethod
    async def search_for_nodes(cls, node_server, search_string):
        for peer in use.search_relevant_peers(Dock.peer_list, search_string):
            yield peer

        for list_id in cls.node_list_ids:
            peers = await cls.get_relevant_peers_for_list_id(node_server, list_id)
            for peer in peers:
                _peers = await node_server.protocol.call_search_peers(peer, search_string)
                yield _peers


def get_more_peers():
    peer_server = Dock.kademlia_network_server
    print("getting more peers")  # debug
    return PeerListGetter.get_more_peers(peer_server)


def search_for_nodes_with_name(search_string):
    """
    searches for nodes relevant to given :param:search_string
    Returns:
         a generator of peers that matches with the search_string
    """
    peer_server = Dock.kademlia_network_server
    return SearchCrawler.search_for_nodes(peer_server, search_string)


class Storage(storage.ForgetfulStorage):
    node_lists_ids = set(node_list_ids)
    peer_data_storage = defaultdict(set)

    def get_list_of_peers(self, list_key):
        if list_key in self.peer_data_storage:
            return list(self.peer_data_storage.get(list_key))
        return None

    def all_peers_in_lists(self):
        return self.peer_data_storage.items()

    def store_peers_in_list(self, list_key, list_of_peers):
        if list_key in self.node_lists_ids:
            print("="*80)  # :todo fix this "list" bug
            print(list_of_peers)
            self.peer_data_storage[list_key] |= set(list_of_peers)
            Dock.peer_list.extend(map(RemotePeer.load_from, list_of_peers))
        return True


async def get_remote_peer(peer_id):
    """
    This function call is expensive as it performs a
    distributed search across the network
    try using Dock.peer_list instead
    """
    return await Dock.kademlia_network_server.get_remote_peer(peer_id)
