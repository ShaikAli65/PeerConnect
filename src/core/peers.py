"""
Helper functions to deal with peers in network
"""

import logging
from dataclasses import dataclass
from typing import AsyncIterator

from kademlia import crawling
from src.avails import PeerDict, RemotePeer, const, use
from src.avails.exceptions import RemotePeerNotFound
from src.avails.remotepeer import convert_peer_id_to_byte_id
from src.core import app_events
from src.core._kademlia import PeerServer
from src.core.peerstore import node_list_ids
from src.core.search import GossipSearch, SearchCrawler
from src.managers.connection import ConnectionManager

_logger = logging.getLogger(__name__)


class PeerListGetter(crawling.ValueSpiderCrawl):
    peers_cache = {}
    previously_fetched_index = 0

    async def find(self):
        return await self._find(self.protocol.call_find_peer_list)

    @use.override
    async def _handle_found_values(self, values):
        peer = self.nearest_without_value.popleft()
        if peer:
            _logger.debug(f"found values {values}")
            await self.protocol.call_store_peers_in_list(peer, self.node.id, values)
        return values

    @classmethod
    async def get_more_peers(cls, peer_server) -> list[RemotePeer]:
        _logger.debug(f"previous index {cls.previously_fetched_index}")
        if cls.previously_fetched_index >= len(node_list_ids) - 1:
            cls.previously_fetched_index = 0

        find_list_id = node_list_ids[cls.previously_fetched_index]
        _logger.debug(f"looking into {find_list_id}")
        cls.previously_fetched_index += 1
        list_of_peers = await peer_server.get_list_of_nodes(find_list_id)

        if list_of_peers:
            cls.peers_cache.update({x.peer_id: x for x in list_of_peers})

            return list(set(list_of_peers))

        return []


@use.provide__init__
class PeerService:
    kad_server: PeerServer
    gossip_searcher: GossipSearch
    connection_manager: ConnectionManager
    peer_list: PeerDict
    app_event_bus: app_events.AppEventsBus

    async def gossip_search(self, search_string) -> AsyncIterator[RemotePeer]:
        async for peer in self.gossip_searcher.search_for(search_string):
            yield peer

    def search_relevant_peers(self, search_string):
        """
        Searches for relevant peers based on the search string,

        Uses a copy of the current peer IDs to avoid modification errors.

        Args:
            search_string (str): The string to search for relevance.
        Yields:
            list: peers
        """

        peer_ids = list(self.peer_list.keys())

        for peer_id in peer_ids:
            try:
                peer = self.peer_list[peer_id]  # May raise KeyError if removed concurrently
            except KeyError:
                continue  # Skip removed peer
            if peer.is_relevant(search_string):
                yield peer

    def search_for_peers_with_name(self, search_string):
        """Searches for nodes relevant to given `search_string`

        Args:
            search_string(str): peer name to search for
        Returns:
             A generator of peers that matches with the search_string
        """

        return SearchCrawler.search_for_nodes(self.kad_server, search_string)

    async def get_remote_peer_from_network(self, peer_id):
        """Gets the `RemotePeer` object corresponding to `RemotePeer.peer_id` from the network

        Wrapper around `kademlia_network_server.get_remote_peer`
        with conversions related to ids, retries on failure

        This call is expensive as it performs a distributed search across the network
        try using `peer_list` instead

        Args:
            peer_id(str): id to search for

        Returns:
            RemotePeer | None
        """
        byte_id = convert_peer_id_to_byte_id(peer_id)
        _logger.debug(f"getting peer with id {peer_id} from network")

        async for _ in use.async_timeouts(max_retries=const.PEER_SEARCH_RETRIES):
            peer = await self.kad_server.get_remote_peer(byte_id)
            if peer is not None:
                return peer

        return None

    async def get_remote_peer(self, peer_id) -> RemotePeer:
        """
        Tries to check for peer_id in cached App.peer_list

        checks for the local cache returns immediately if found online,

        if peer is flagged as offline or not found in the cache at all,
        then performs a distributed search, on failure, returns offline peer object
        """
        try:
            peer_obj = self.peer_list.get_peer(peer_id)
            if peer_obj.is_online:
                return peer_obj
        except KeyError:
            peer_obj = None

        peer_obj_from_network = await self.get_remote_peer_from_network(peer_id)
        if peer_obj_from_network:
            peer_obj = peer_obj_from_network

        if peer_obj is None:
            err = RemotePeerNotFound()
            err.peer_id = peer_id
            raise err
        else:
            self.change_peer_status(peer_obj, RemotePeer.STATUS.ONLINE)
        return peer_obj

    async def remove_peer(self, peer_id):
        peer = await self.get_remote_peer(peer_id)
        if peer is None:
            return

        is_reachable = await self.connection_manager.is_peer_reachable(peer)
        if not is_reachable:
            self.change_peer_status(peer, RemotePeer.STATUS.OFFLINE)

    def change_peer_status(self, peer, status):
        if peer.status == status:
            return
        peer.status = status
        self.app_event_bus.publish(app_events.PeerStatusUpdate(peer))

    def add_peer(self, peer):
        self.peer_list.add_peer(peer)
        self.app_event_bus.publish(app_events.PeerStatusUpdate(peer))

