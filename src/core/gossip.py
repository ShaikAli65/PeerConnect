import logging

from src.avails import GossipMessage, const
from src.avails.mixins import BasicDispatcher
from src.core import search
from src.core.app import AppType
from src.net.events import GossipEvent, RequestEvent
from src.transfers import GOSSIP_HEADER, GossipTransport, REQUESTS_HEADERS, \
    RumorMongerProtocol, SimpleRumorMessageList

_logger = logging.getLogger(__name__)


class GlobalGossipRumorMessageList(SimpleRumorMessageList):
    __slots__ = "global_peer_list",

    def __init__(self, global_peer_list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.global_peer_list = global_peer_list

    def _get_list_of_peers(self):
        return set(self.global_peer_list.keys())


class GlobalRumorMonger(RumorMongerProtocol):
    def __init__(self, transport, global_peer_list):
        message_list = GlobalGossipRumorMessageList(global_peer_list, const.NODE_POV_GOSSIP_TTL)
        super().__init__(transport, global_peer_list, message_list)


def GlobalGossipMessageHandler(gossip_handler):
    async def handle(event: GossipEvent):
        print("[GOSSIP] new message arrived", event.message, "from", event.from_addr)
        return gossip_handler.message_arrived(*event)

    return handle


class GossipDispatcher(*BasicDispatcher):
    """Dispatches gossip messages from multiplexed requests endpoint"""

    async def submit(self, event: RequestEvent):
        gossip_message = GossipMessage(event.request)
        g_event = GossipEvent(gossip_message, event.from_addr)
        return await self.call_handler(gossip_message.header, _logger, g_event)


async def initiate_gossip(data_transport, req_dispatcher, peer_list, exit_stack):
    gossip_transport = GossipTransport(data_transport)
    g_dispatcher = GossipDispatcher()

    gossiper = GlobalRumorMonger(gossip_transport, peer_list)

    gossip_message_handler = GlobalGossipMessageHandler(gossiper)

    search.register_handlers(
        gossiper,
        g_dispatcher,
        gossip_message_handler,
        gossip_transport
    )

    g_dispatcher.register_handler(GOSSIP_HEADER.MESSAGE, gossip_message_handler)
    req_dispatcher.register_handler(REQUESTS_HEADERS.GOSSIP, g_dispatcher)
    await exit_stack.enter_async_context(g_dispatcher)
    return gossip_transport, g_dispatcher, gossiper
