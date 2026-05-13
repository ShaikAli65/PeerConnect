import logging
from typing import NamedTuple

from src import net
from src.avails import GossipMessage, const
from src.avails.bases import Router
from src.avails.useables import override
from src.core import search
from src.gossip.rumor import GossipTransport, RumorMongerProtocol, SimpleRumorMessageList
from src.transfers import GOSSIP_HEADER

_logger = logging.getLogger(__name__)


class GlobalGossipRumorMessageList(SimpleRumorMessageList):

    def __init__(self, global_peer_list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.global_peer_list = global_peer_list

    def _get_list_of_peers(self):
        return set(self.global_peer_list.keys())


def GlobalGossipMessageHandler(gossip_handler):
    async def handle(event: net.GossipEvent):
        _logger.info("new message arrived %s %s %s", event.message, "from", event.from_addr)
        return gossip_handler.message_arrived(*event)

    return handle


class GossipRouter(Router):
    __slots__ = ()

    @override
    async def __call__(self, event: net.RequestEvent):  # noqa
        gossip_message = GossipMessage(event.request)
        g_event = net.GossipEvent(gossip_message, event.from_addr)
        return await self.registry[gossip_message.header](g_event)


class GossipService(NamedTuple):
    gossip_transport: GossipTransport
    gossip_router: GossipRouter
    gossiper: RumorMongerProtocol


async def initiate_gossip(data_transport, remote_peer, req_dispatcher, peer_list):
    gossip_transport = GossipTransport(data_transport)
    gossip_router = GossipRouter()

    message_list = GlobalGossipRumorMessageList(peer_list, const.NODE_POV_GOSSIP_TTL)
    gossiper = RumorMongerProtocol(gossip_transport, peer_list, message_list)

    gossip_message_handler = GlobalGossipMessageHandler(gossiper)
    gossip_router.register_handler(GOSSIP_HEADER.MESSAGE, gossip_message_handler)

    gossip_service = GossipService(gossip_transport, gossip_router, gossiper)
    gossip_searcher = search.init_gossip_searcher(
        remote_peer,
        gossip_service,
        gossip_message_handler,
    )
    req_dispatcher.register_handler(net.REQUESTS_HEADERS.GOSSIP, gossip_router)
    return gossip_service, gossip_searcher
