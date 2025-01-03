import asyncio
import functools
import inspect
import logging

from src.avails import InvalidPacket, QueueMixIn, const, unpack_datagram
from src.avails.bases import BaseDispatcher
from src.avails.connect import UDPProtocol, ipv4_multicast_socket_helper, ipv6_multicast_socket_helper
from src.avails.events import RequestEvent
from src.core import DISPATCHS, Dock, _kademlia, discover, gossip
from src.core.discover import DiscoveryReplyHandler, DiscoveryRequestHandler
from src.core.transfers import DISCOVERY, REQUESTS_HEADERS
from src.core.transfers.transports import RequestsTransport

_logger = logging.getLogger(__name__)


async def initiate():
    const.BIND_IP = const.THIS_IP

    bind_address = (const.BIND_IP, const.PORT_REQ)
    multicast_address = (const.MULTICAST_IP_v4 if const.USING_IP_V4 else const.MULTICAST_IP_v6, const.PORT_NETWORK)
    broad_cast_address = (const.BROADCAST_IP, const.PORT_NETWORK)

    req_dispatcher = RequestsDispatcher(None, Dock.finalizing.is_set)
    transport = await setup_transport(bind_address, multicast_address, req_dispatcher)
    req_dispatcher.transport = RequestsTransport(transport)
    Dock.dispatchers[DISPATCHS.REQUESTS] = req_dispatcher

    kad_server = _kademlia.prepare_kad_server(transport, req_dispatcher)
    await gossip_initiate(req_dispatcher, transport)

    Dock.requests_endpoint = transport
    Dock.kademlia_network_server = kad_server

    await discovery_initiate(
        broad_cast_address,
        kad_server,
        multicast_address,
        req_dispatcher,
        transport
    )


async def setup_transport(bind_address, multicast_address, req_dispatcher):
    loop = asyncio.get_running_loop()
    base_socket = _create_listen_socket(bind_address, multicast_address)
    transport, proto = await loop.create_datagram_endpoint(
        functools.partial(RequestsEndPoint, req_dispatcher),
        sock=base_socket
    )
    return transport


async def gossip_initiate(req_dispatcher, transport):
    gossip_dispatcher = gossip.initiate_gossip(transport, req_dispatcher)
    Dock.dispatchers[DISPATCHS.GOSSIP] = gossip_dispatcher


async def discovery_initiate(broad_cast_address, kad_server, multicast_address, req_dispatcher, transport):
    discover_dispatcher = discover.DiscoveryDispatcher(transport, Dock.finalizing.is_set)
    req_dispatcher.register_handler(REQUESTS_HEADERS.DISCOVERY, discover_dispatcher)
    Dock.dispatchers[DISPATCHS.DISCOVER] = discover_dispatcher

    discovery_reply_handler = DiscoveryReplyHandler(kad_server)
    discovery_req_handler = DiscoveryRequestHandler(discover_dispatcher.transport)

    discover_dispatcher.register_handler(DISCOVERY.NETWORK_FIND_REPLY, discovery_reply_handler)
    discover_dispatcher.register_handler(DISCOVERY.NETWORK_FIND, discovery_req_handler)

    await discover.send_discovery_requests(
        discover_dispatcher.transport,
        broad_cast_address,
        multicast_address
    )


def _create_listen_socket(bind_address, multicast_addr):
    loop = asyncio.get_running_loop()
    sock = UDPProtocol.create_async_server_sock(
        loop, bind_address, family=const.IP_VERSION
    )

    if const.USING_IP_V4:
        ipv4_multicast_socket_helper(sock, multicast_addr)
        _logger.info("[REQUESTS] registered request socket for multicast v4")
    else:
        ipv6_multicast_socket_helper(sock, multicast_addr)
        _logger.info("[REQUESTS] registered request socket for multicast v6")
    return sock


class RequestsDispatcher(QueueMixIn, BaseDispatcher):
    def __init__(self, transport, stop_flag):
        super().__init__(transport, stop_flag)

    async def submit(self, req_event: RequestEvent):
        handler = self.registry[req_event.root_code]
        _logger.info(f"[REQUESTS] dispatching request with code: {req_event.root_code} to {handler}")
        # expected type of handlers
        # 1. Dispatcher objects that are coupled with QueueMixIn (sync)
        # 2. Dispatcher objects that are not coupled with QueueMixIn (async)
        # 3. any type of handlers (async)

        f = handler(req_event)
        if inspect.isawaitable(f):
            await f


class RequestsEndPoint(asyncio.DatagramProtocol):

    def __init__(self, dispatcher):
        """A Requests Endpoint

            Handles all the requests/messages come to the application's requests endpoint
            separates messages related to kademila and calls respective callbacks that are supposed to be called

            Args:
                dispatcher(RequestsDispatcher) : dispatcher object that gets `called` when a datagram arrives
        """

        self.dispatcher = dispatcher

    def connection_made(self, transport):
        self.transport = transport
        _logger.info(f"[REQUESTS] started requests endpoint at {transport.get_extra_info("socket")}")

    def datagram_received(self, actual_data, addr):
        code, stripped_data = actual_data[:1], actual_data[1:]
        try:
            req_data = unpack_datagram(stripped_data)
        except InvalidPacket as ip:
            _logger.info(f"[REQUESTS] error:", exc_info=ip)
            return

        _logger.info(f"[REQUESTS] received: {code} : '{str(req_data)[:15]}...'",extra={'from':addr})
        event = RequestEvent(root_code=code, request=req_data, from_addr=addr)
        self.dispatcher(event)


async def end_requests():
    Dock.kademlia_network_server.stop()
    Dock.requests_endpoint.close()
    Dock.requests_endpoint = None
