import asyncio
import functools
import operator
from typing import NamedTuple

import src.core.gossip
from src.avails import RequestHandler, Wire, WireData, const, unpack_datagram, use, wire
from src.avails.abcs import Dispatcher
from src.avails.connect import UDPProtocol, ipv4_multicast_socket_helper, ipv6_multicast_socket_helper
from src.core import Dock, _kademlia, discover, get_gossip, get_this_remote_peer, gossip, peers
from src.core.transfers import HEADERS, REQUESTS_HEADERS
from src.managers import filemanager


async def initiate():
    loop = asyncio.get_running_loop()

    bind_address = (const.BIND_IP, const.PORT_REQ)
    multicast_address = (const.MULTICAST_IP_v4 if const.USING_IP_V4 else const.MULTICAST_IP_v6, const.PORT_NETWORK)
    broad_cast_address = (const.BROADCAST_IP, const.PORT_NETWORK)
    peer_addresses = await discover.search_network(
        bind_address,
        broad_cast_address,
        multicast_address
    )
    print("search request responses", peer_addresses)

    kad_server = _kademlia.get_new_kademlia_server()
    kad_server.start()

    req_dispatcher = RequestsDispatcher()
    # req_dispatcher.register_handler(REQUESTS_HEADERS.KADEMLIA)

    transport, proto = await loop.create_datagram_endpoint(
        functools.partial(RequestsEndPoint, req_dispatcher),
        sock=_create_listen_socket(bind_address, multicast_address)
    )

    kad_server.protocol.connection_made(transport)

    if any(peer_addresses):
        valid_addresses = filter(operator.truth, peer_addresses)  # [x for x in peer_addresses if x]
        print("bootstrapping kademlia with", valid_addresses)  # debug
        if await kad_server.bootstrap(valid_addresses):
            Dock.server_in_network = True

    gossip.join_gossip(transport)
    Dock.protocol = proto
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


class RequestEvent(NamedTuple):
    request: WireData
    from_addr: tuple[str, int]


class RequestsDispatcher(Dispatcher):
    def __init__(self):
        self.handlers = {}

    def register_handler(self, header, handler: RequestHandler):
        self.handlers[header] = handler

    def dispatch(self, req_event):
        handler = self.handlers.get(req_event.header)
        handler(req_event)


class RequestsEndPoint(asyncio.DatagramProtocol):

    def __init__(self, kademlia_server, dispatcher):
        """A Requests Endpoint

            Handles all the requests/messages come to the application's requests endpoint
            separates messages related to kademila and calls respective callbacks that are supposed to be called

            Args:
                dispatcher(Dispatcher) : dispatcher object that gets `called` when a datagram arrives
        """

        self.dispatcher = dispatcher

    def connection_made(self, transport):
        self.transport = transport
        print(
            "started requests endpoint at", transport.get_extra_info("socket")
        )  # debug

    def datagram_received(self, data_payload, addr):
        req_data = unpack_datagram(data_payload)
        print("Received: %s from %s" % (req_data, addr))
        self.dispatcher(data_payload, addr)

        # self.handle_request(req_data, addr)

    def handle_request(self, req_data: WireData, addr):
        """Handle different request types based on the header"""
        if req_data.match_header(REQUESTS_HEADERS.NETWORK_FIND):
            self.handle_network_find(addr)
        elif req_data.match_header(REQUESTS_HEADERS.NETWORK_FIND_REPLY):
            self.handle_network_find_reply(req_data)

        elif req_data.match_header(HEADERS.OTM_FILE_TRANSFER):
            self.handle_onetomanyfile_session(req_data, addr)

        elif req_data.match_header(REQUESTS_HEADERS.GOSSIP_MESSAGE):
            self.handle_gossip_message(req_data)
        elif req_data.match_header(REQUESTS_HEADERS.GOSSIP_SEARCH_REQ):
            self.handle_gossip_search_req(req_data, addr)
        elif req_data.match_header(REQUESTS_HEADERS.GOSSIP_SEARCH_REPLY):
            self.handle_gossip_search_reply(req_data, addr)
        elif req_data.match_header(HEADERS.GOSSIP_CREATE_SESSION):
            self.handle_gossip_session(req_data, addr)

    def handle_network_find(self, addr):
        """ Handle NETWORK_FIND request """
        # :todo: write consensus protocol for replying a network find request
        this_rp = get_this_remote_peer()
        data_payload = WireData(
            header=REQUESTS_HEADERS.NETWORK_FIND_REPLY,
            _id=this_rp.id,
            connect_uri=this_rp.req_uri
        )
        if self.transport:
            Wire.send_datagram(self.transport, addr, bytes(data_payload))
            print("Sent NETWORK_FIND_REPLY: %s to %s" % (data_payload, addr))
        else:
            print("Transport not available for sending reply to %s" % addr)

    @staticmethod
    def handle_network_find_reply(req_data):
        """ Handle NETWORK_FIND_REPLY request """
        bootstrap_node_addr = tuple(req_data['connect_uri'])
        f = use.wrap_with_tryexcept(Dock.kademlia_network_server.bootstrap, [bootstrap_node_addr])
        asyncio.create_task(f())
        print(f"Bootstrap initiated to: {bootstrap_node_addr}")

    def handle_onetomanyfile_session(self, req_data, addr):
        reply = filemanager.new_otm_request_arrived(req_data, addr)
        Wire.send_datagram(self.transport, addr, reply)

    @staticmethod
    def handle_gossip_message(req_data):
        """ Handle GOSSIP_MESSAGE request """
        gossip_protocol = get_gossip()
        gossip_message = wire.GossipMessage(req_data)
        gossip_protocol.message_arrived(gossip_message)

    @staticmethod
    def handle_gossip_session(req_data, addr):
        f = use.wrap_with_tryexcept(src.core.gossip.new_gossip_request_arrived, req_data, addr)
        asyncio.create_task(f())

    @staticmethod
    def handle_gossip_search_reply(reply_data, addr):
        handler = peers.get_search_handler()
        gossip_reply = wire.GossipMessage(reply_data)
        handler.reply_arrived(gossip_reply, addr)

    def handle_gossip_search_req(self, req_data, addr):
        handler = peers.get_search_handler()
        gossip_reply = wire.GossipMessage(req_data)
        reply = handler.request_arrived(gossip_reply, addr)
        Wire.send_datagram(self.transport, addr, reply)


async def end_requests():
    Dock.server_in_network = False
    Dock.kademlia_network_server.stop()
    Dock.requests_endpoint.close()
    Dock.requests_endpoint = None
