import asyncio
import functools

import src.core.gossip
from src.avails import Wire, WireData, const, unpack_datagram, use
from src.avails.bases import BaseDispatcher, RequestEvent
from src.avails.connect import UDPProtocol, ipv4_multicast_socket_helper, ipv6_multicast_socket_helper
from src.core import DISPATCHS, Dock, _kademlia, discover, gossip
from src.core._kademlia import KadDiscoveryReplyHandler
from src.core.transfers import HEADERS, REQUESTS_HEADERS
from src.core.transfers.transports import RequestsTransport
from src.managers import filemanager


async def initiate():
    const.BIND_IP = const.THIS_IP

    loop = asyncio.get_running_loop()

    bind_address = (const.BIND_IP, const.PORT_REQ)
    multicast_address = (const.MULTICAST_IP_v4 if const.USING_IP_V4 else const.MULTICAST_IP_v6, const.PORT_NETWORK)
    broad_cast_address = (const.BROADCAST_IP, const.PORT_NETWORK)

    req_dispatcher = RequestsDispatcher(None, Dock.finalizing.is_set)
    base_socket = _create_listen_socket(bind_address, multicast_address)
    transport, proto = await loop.create_datagram_endpoint(
        functools.partial(RequestsEndPoint, req_dispatcher),
        sock=base_socket
    )
    req_dispatcher.transport = RequestsTransport(transport)
    Dock.dispatchers[DISPATCHS.REQUESTS] = req_dispatcher

    kad_server = _kademlia.prepare_kad_server(transport, req_dispatcher)
    discovery_reply_handler = KadDiscoveryReplyHandler(kad_server)

    discover_dispatcher = discover.DiscoveryDispatcher(transport, Dock.finalizing.is_set)
    req_dispatcher.register_handler(REQUESTS_HEADERS.DISCOVERY, discover_dispatcher)
    Dock.dispatchers[DISPATCHS.DISCOVER] = discover_dispatcher
    discover_dispatcher.register_handler(REQUESTS_HEADERS.NETWORK_FIND_REPLY, discovery_reply_handler)
    await discover.search_network(
        discover_dispatcher.transport,
        broad_cast_address,
        multicast_address
    )

    gossip_dispatcher = gossip.initiate_gossip(transport, req_dispatcher)
    Dock.dispatchers[DISPATCHS.GOSSIP] = gossip_dispatcher

    Dock.requests_endpoint = transport
    Dock.kademlia_network_server = kad_server

    # f = use.wrap_with_tryexcept(kad_server.add_this_peer_to_lists)
    # asyncio.create_task(f())


def _create_listen_socket(bind_address, multicast_addr):
    loop = asyncio.get_running_loop()
    sock = UDPProtocol.create_async_server_sock(
        loop, bind_address, family=const.IP_VERSION
    )

    if const.USING_IP_V4:
        ipv4_multicast_socket_helper(sock, multicast_addr)
        print("registered request socket for multicast v4")
    else:
        ipv6_multicast_socket_helper(sock, multicast_addr)
        print("registered request socket for multicast v6")
    return sock


class RequestsDispatcher(BaseDispatcher):
    def __init__(self, transport, stop_flag):
        super().__init__(transport, stop_flag)

    async def submit(self, req_event: RequestEvent):
        handler = self.registry[req_event.root_code]
        await handler(req_event)


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
        print(
            "started requests endpoint at", transport.get_extra_info("socket")
        )  # debug

    def datagram_received(self, data_payload, addr):
        code, data = data_payload[:1], data_payload[1:]
        req_data = unpack_datagram(data_payload)
        print("Received: %s from %s" % (req_data, addr))
        event = RequestEvent(root_code=code, request=req_data, from_addr=addr)
        self.dispatcher(event)
        # self.handle_request(req_data, addr)

    def handle_request(self, req_data: WireData, addr):
        """Handle different request types based on the header"""
        # if req_data.match_header(REQUESTS_HEADERS.NETWORK_FIND):
        #     self.handle_network_find(addr)
        # elif req_data.match_header(REQUESTS_HEADERS.NETWORK_FIND_REPLY):
        #     self.handle_network_find_reply(req_data)

        if req_data.match_header(HEADERS.OTM_FILE_TRANSFER):
            self.handle_onetomanyfile_session(req_data, addr)

        # elif req_data.match_header(REQUESTS_HEADERS.GOSSIP_MESSAGE):
        #     self.handle_gossip_message(req_data)
        # elif req_data.match_header(REQUESTS_HEADERS.GOSSIP_SEARCH_REQ):
        #     self.handle_gossip_search_req(req_data, addr)
        # elif req_data.match_header(REQUESTS_HEADERS.GOSSIP_SEARCH_REPLY):
        #     self.handle_gossip_search_reply(req_data, addr)
        elif req_data.match_header(HEADERS.GOSSIP_CREATE_SESSION):
            self.handle_gossip_session(req_data, addr)

    # def handle_network_find(self, addr):
    #     """ Handle NETWORK_FIND request """
    #     # :todo: write consensus protocol for replying a network find request
    #     this_rp = get_this_remote_peer()
    #     data_payload = WireData(
    #         header=REQUESTS_HEADERS.NETWORK_FIND_REPLY,
    #         _id=this_rp.id,
    #         connect_uri=this_rp.req_uri
    #     )
    #     if self.transport:
    #         Wire.send_datagram(self.transport, addr, bytes(data_payload))
    #         print("Sent NETWORK_FIND_REPLY: %s to %s" % (data_payload, addr))
    #     else:
    #         print("Transport not available for sending reply to %s" % addr)
    #
    # @staticmethod
    # def handle_network_find_reply(req_data):
    #     """ Handle NETWORK_FIND_REPLY request """
    #     bootstrap_node_addr = tuple(req_data['connect_uri'])
    #     f = use.wrap_with_tryexcept(Dock.kademlia_network_server.bootstrap, [bootstrap_node_addr])
    #     asyncio.create_task(f())
    #     print(f"Bootstrap initiated to: {bootstrap_node_addr}")

    def handle_onetomanyfile_session(self, req_data, addr):
        reply = filemanager.new_otm_request_arrived(req_data, addr)
        Wire.send_datagram(self.transport, addr, reply)

    # @staticmethod
    # def handle_gossip_message(req_data):
    #     """ Handle GOSSIP_MESSAGE request """
    #     gossip_protocol = get_gossip()
    #     gossip_message = wire.GossipMessage(req_data)
    #     gossip_protocol.message_arrived(gossip_message)

    @staticmethod
    def handle_gossip_session(req_data, addr):
        f = use.wrap_with_tryexcept(src.core.gossip.new_gossip_request_arrived, req_data, addr)
        asyncio.create_task(f())
    #
    # @staticmethod
    # def handle_gossip_search_reply(reply_data, addr):
    #     handler = peers.get_search_handler()
    #     gossip_reply = wire.GossipMessage(reply_data)
    #     handler.reply_arrived(gossip_reply, addr)
    #
    # def handle_gossip_search_req(self, req_data, addr):
    #     handler = peers.get_search_handler()
    #     gossip_reply = wire.GossipMessage(req_data)
    #     reply = handler.request_arrived(gossip_reply, addr)
    #     # self.transport.sendto(reply, addr)
    #     Wire.send_datagram(self.transport, addr, reply)


async def end_requests():
    Dock.kademlia_network_server.stop()
    Dock.requests_endpoint.close()
    Dock.requests_endpoint = None
