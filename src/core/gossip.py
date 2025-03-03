from src.avails import BaseDispatcher, GossipMessage, const
from src.avails.events import GossipEvent
from src.avails.mixins import QueueMixIn
from src.core.peers import get_search_handler
from src.core.public import get_gossip
from src.transfers import GOSSIP, GossipTransport, REQUESTS_HEADERS, \
    RumorMongerProtocol, SimpleRumorMessageList


class GlobalGossipRumorMessageList(SimpleRumorMessageList):  # inspired from java
    __slots__ = "global_peer_list", 
    def __init__(self, global_peer_list, *args,**kwargs):
        super().__init__(*args,**kwargs)
        self.global_peer_list = global_peer_list

    def _get_list_of_peers(self):
        return set(self.global_peer_list.keys())


class GlobalRumorMonger(RumorMongerProtocol):
    def __init__(self, transport, global_peer_list):
        super().__init__(transport, global_peer_list, GlobalGossipRumorMessageList(global_peer_list, const.NODE_POV_GOSSIP_TTL))


def GlobalGossipMessageHandler(global_gossiper):
    async def handle(event: GossipEvent):
        print("[GOSSIP] new message arrived", event.message, "from", event.from_addr)
        return global_gossiper.message_arrived(*event)

    return handle


def GossipSearchReqHandler(searcher, transport, gossiper,
                           gossip_handler):
    """
    Working:
        * GossipEvent is passed into the handler when someone tries to search for some user
        * We only reply if the search string relates to us.
        * All the decision-making is done by searcher, just a helper to send reply returned by searcher
        * Gossips the received search request received using gossiper

    Args:
        searcher(GossipSearch): delegates search request event to this object
        transport(GossipTransport): transport to use to send messages
        gossiper(RumorMongerProtocol): helper to gossip event message
        gossip_handler(GlobalGossipMessageHandler): handler that handles gossip message that has arrived

    """
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
    async def submit(self, event):
        gossip_message = GossipMessage(event.request)
        handler = self.registry[gossip_message.header]
        g_event = GossipEvent(gossip_message, event.from_addr)
        await handler(g_event)


def initiate_gossip(data_transport, req_dispatcher, app_ctx):
    global_gossip = app_ctx.global_gossip
    gossip_transport = GossipTransport(data_transport)
    global_gossip = GlobalRumorMonger(gossip_transport, app_ctx.peer_list)

    g_dispatcher = GossipDispatcher()

    gossip_searcher = get_search_handler()

    gossip_message_handler = GlobalGossipMessageHandler(global_gossip)
    req_handler = GossipSearchReqHandler(
        gossip_searcher,
        gossip_transport,
        global_gossip,
        gossip_message_handler
    )
    reply_handler = GossipSearchReplyHandler(gossip_searcher)
    g_dispatcher.register_handler(GOSSIP.MESSAGE, gossip_message_handler)
    g_dispatcher.register_handler(GOSSIP.SEARCH_REQ, req_handler)
    g_dispatcher.register_handler(GOSSIP.SEARCH_REPLY, reply_handler)

    req_dispatcher.register_handler(REQUESTS_HEADERS.GOSSIP, g_dispatcher)
    print("joined gossip network", get_gossip())
    return g_dispatcher
