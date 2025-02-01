from typing import Callable, Coroutine

from src.avails import BaseDispatcher, GossipMessage
from src.avails.events import GossipEvent
from src.avails.mixins import QueueMixIn
from src.core import Dock, get_gossip
from src.core.peers import get_search_handler
from src.transfers import GOSSIP, GossipTransport, REQUESTS_HEADERS, \
    RumorMongerProtocol, SimpleRumorMessageList


class GlobalGossipRumorMessageList(SimpleRumorMessageList):  # inspired from java
    @staticmethod
    def _get_list_of_peers():
        return set(Dock.peer_list.keys())


class GlobalRumorMonger(RumorMongerProtocol):
    def __init__(self, transport):
        super().__init__(transport, GlobalGossipRumorMessageList)


def GlobalGossipMessageHandler(global_gossiper):
    async def handle(event: GossipEvent):
        print("[GOSSIP] new message arrived", event.message, "from", event.from_addr)
        return global_gossiper.message_arrived(*event)

    return handle


def GossipSearchReqHandler(searcher, transport, gossiper: RumorMongerProtocol,
                           gossip_handler: GlobalGossipMessageHandler):
    async def handle(event: GossipEvent):
        if not gossiper.is_seen(event.message):
            await gossip_handler(event)
        if reply := searcher.request_arrived(*event):
            return transport.sendto(reply, event.from_addr)

    return handle


def GossipSearchReplyHandler(searcher):
    async def handle(event: GossipEvent):
        print("[GOSSIP][SEARCH] reply received:", event.message, "for", event.from_addr)
        return searcher.reply_arrived(*event)

    return handle


class GossipDispatcher(QueueMixIn, BaseDispatcher):
    """
        elif req_data.match_header(HEADERS.GOSSIP_CREATE_SESSION):
            self.handle_gossip_session(req_data, addr)
            GOSSIP.CREATE_SESSION: None,
    """
    __slots__ = 'registry',

    def __init__(self, transport: GossipTransport, stop_flag):
        super().__init__(transport=transport, stop_flag=stop_flag)
        self.transport = transport
        self.registry: dict[bytes, Callable[[GossipEvent], Coroutine[None, None, None]]] = {}

    async def submit(self, event):
        gossip_message = GossipMessage(event.request)
        handler = self.registry[gossip_message.header]
        g_event = GossipEvent(gossip_message, event.from_addr)
        await handler(g_event)


def initiate_gossip(data_transport, req_dispatcher):
    gossip_transport = GossipTransport(data_transport)
    Dock.global_gossip = GlobalRumorMonger(gossip_transport)

    g_dispatcher = GossipDispatcher(gossip_transport, Dock.finalizing.is_set)

    gossip_searcher = get_search_handler()

    gossip_message_handler = GlobalGossipMessageHandler(Dock.global_gossip)
    req_handler = GossipSearchReqHandler(
        gossip_searcher,
        gossip_transport,
        Dock.global_gossip,
        gossip_message_handler
    )
    reply_handler = GossipSearchReplyHandler(gossip_searcher)
    g_dispatcher.register_handler(GOSSIP.MESSAGE, gossip_message_handler)
    g_dispatcher.register_handler(GOSSIP.SEARCH_REQ, req_handler)
    g_dispatcher.register_handler(GOSSIP.SEARCH_REPLY, reply_handler)

    req_dispatcher.register_handler(REQUESTS_HEADERS.GOSSIP, g_dispatcher)
    print("joined gossip network", get_gossip())
    return g_dispatcher
