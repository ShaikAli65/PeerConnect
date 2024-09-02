import functools
from typing import override

from kademlia import crawling

from src.avails import RemotePeer
from src.core import Dock
from src.managers.statemanager import State

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
        if cls.previously_fetched_index >= len(cls.node_list_ids) - 1:
            cls.previously_fetched_index = 0

        find_list_id = cls.node_list_ids[cls.previously_fetched_index]
        list_of_peers = await peer_server.get_list_of_nodes(find_list_id)
        cls.previously_fetched_index += 1

        if list_of_peers:
            cls.initial_list.extend(list_of_peers)
            return list_of_peers

        return []


class SearchCrawler:
    node_list_ids = node_list_ids
    responsible_peers_mapping_to_list_ids = {}
    list_id_mapper_handle = None

    @classmethod
    def add_responsible_peers_for_peer_lists_to_cache(cls, list_id, responsible_peers):
        cls.responsible_peers_mapping_to_list_ids[list_id] = responsible_peers

    @classmethod
    async def get_relevant_peers_for_list_ids(cls, node_server, list_id_index):
        if list_id_index == len(cls.node_list_ids):
            return
        list_id = cls.node_list_ids[list_id_index]
        peer = RemotePeer(list_id)
        nearest = node_server.protocol.router.find_neighbors(peer)
        crawler = crawling.NodeSpiderCrawl(node_server.protocol, peer, nearest, node_server.ksize, node_server.alpha)
        responsible_nodes = await crawler.find()
        cls.add_responsible_peers_for_peer_lists_to_cache(list_id, responsible_nodes)
        await Dock.state_handle.put_state(
            State(
                'get_relevant_peers_for_list_ids',
                functools.partial(
                    cls.get_relevant_peers_for_list_ids,
                    node_server,
                    list_id_index + 1,
                )
            )
        )

    @classmethod
    async def search_for_nodes(cls, node_server, search_string):
        if len(cls.responsible_peers_mapping_to_list_ids) == 0:
            await cls.get_relevant_peers_for_list_ids(node_server, 0)
        list_of_set_of_responsible_peers = list(cls.responsible_peers_mapping_to_list_ids.values())
        for set_of_responsible_peers in list_of_set_of_responsible_peers:
            peer = set_of_responsible_peers[0]
            await node_server.protocol.call_search_peers(peer, search_string)


def get_more_peers():
    peer_server = Dock.kademlia_network_server
    return PeerListGetter.get_more_peers(peer_server)


def search_for_nodes_with_name(search_string):
    """
    searches for nodes relevant to given :param:search_string
    :returns: a list of peers that matches with the search_string
    """
    peer_server = Dock.kademlia_network_server
    return SearchCrawler.search_for_nodes(peer_server, search_string)