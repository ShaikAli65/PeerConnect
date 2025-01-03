import logging

from src.avails import QueueMixIn, WireData, const, use
from src.avails.bases import BaseDispatcher
from src.avails.events import RequestEvent
from src.core import get_this_remote_peer
from src.core.transfers import DISCOVERY
from src.core.transfers.transports import DiscoveryTransport

_logger = logging.getLogger(__name__)


def DiscoveryReplyHandler(kad_server):
    async def handle(event: RequestEvent):
        if event.from_addr[0] == const.THIS_IP:
            return
        connect_address = tuple(event.request["connect_uri"])
        _logger.debug("[DISCOVERY] bootstrapping kademlia")
        await kad_server.bootstrap([connect_address])
        _logger.debug("[DISCOVERY] bootstrapping completed")

    return handle


def DiscoveryRequestHandler(discovery_transport):
    async def handle(event: RequestEvent):
        if event.from_addr[0] == const.THIS_IP:
            return
        req_packet = event.request
        _logger.info("[DISCOVERY] replying to req with addr:", req_packet.body)
        this_rp = get_this_remote_peer()
        data_payload = WireData(
            header=DISCOVERY.NETWORK_FIND_REPLY,
            msg_id=this_rp.peer_id,
            connect_uri=this_rp.req_uri,
        )
        discovery_transport.sendto(
            bytes(data_payload), tuple(req_packet["reply_addr"])
        )

    return handle


class DiscoveryDispatcher(QueueMixIn, BaseDispatcher):
    def __init__(self, transport, stopping_flag):
        super().__init__(
            transport=DiscoveryTransport(transport), stop_flag=stopping_flag
        )

    async def submit(self, event: RequestEvent):
        wire_data = event.request
        handle = self.registry[wire_data.header]
        _logger.debug(f"[DISCOVERY] dispatching request", extra={'id': event.root_code})
        await handle(event)


async def send_discovery_requests(transport, broad_cast_addr, multicast_addr):
    this_rp = get_this_remote_peer()
    ping_data = WireData(
        DISCOVERY.NETWORK_FIND,
        this_rp.peer_id,
        reply_addr=this_rp.req_uri
    )

    if const.USING_IP_V4:
        async for _ in use.async_timeouts(max_retries=const.DISCOVER_RETRIES):
            transport.sendto(bytes(ping_data), broad_cast_addr)
        _logger.debug("[DISCOVERY] sent discovery request to broadcast", extra={'addr': broad_cast_addr})
    async for _ in use.async_timeouts(max_retries=const.DISCOVER_RETRIES):
        transport.sendto(bytes(ping_data), multicast_addr)
    _logger.debug("[DISCOVERY] sent discovery request to multicast", extra={'addr': multicast_addr})
