import asyncio
import socket

from src.avails import Wire, WireData, const, unpack_datagram, use, wire
from src.core import Dock, _kademlia, get_gossip, get_this_remote_peer, peers
from src.core.discover import search_network
from src.core.gossip import join_gossip
from src.core.transfers import HEADERS, REQUESTS_HEADERS
from src.managers import filemanager, gossipmanager


async def initiate():
    loop = asyncio.get_running_loop()
    server = _kademlia.get_new_kademlia_server()
    await server.listen(port=const.PORT_NETWORK, interface=const.THIS_IP)
    print("started kademlia endpoint at ", const.PORT_NETWORK)

    node_addr = await search_network()
    if node_addr is not None:
        print("bootstrapping kademlia with", node_addr)  # debug
        if await server.bootstrap(
                [
                    node_addr,
                ]
        ):
            Dock.server_in_network = True

    transport, proto = await loop.create_datagram_endpoint(
        RequestsEndPoint,
        # local_addr=('0.0.0.0' if const.IP_VERSION == socket.AF_INET else '::', const.PORT_REQ),
        local_addr=(const.THIS_IP, const.PORT_REQ),
        family=const.IP_VERSION,
        proto=socket.IPPROTO_UDP,
        allow_broadcast=True,
    )
    join_gossip(transport)

    Dock.protocol = proto
    Dock.requests_endpoint = transport
    Dock.kademlia_network_server = server
    f = use.wrap_with_tryexcept(server.add_this_peer_to_lists)
    asyncio.create_task(f())
    return server, transport, proto


class RequestsRegistry:
    ...


class RequestsEndPoint(asyncio.DatagramProtocol):
    __slots__ = 'transport',
    requests_registry = {}

    def connection_made(self, transport):
        self.transport = transport
        print(
            "started requests endpoint at", transport.get_extra_info("socket")
        )  # debug

    def datagram_received(self, data_payload, addr):
        req_data = unpack_datagram(data_payload)
        if not req_data:
            return  # Failed to unpack
        print("Received: %s from %s" % (req_data, addr))
        self.handle_request(req_data, addr)

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
            connect_uri=this_rp.network_uri
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
        f = use.wrap_with_tryexcept(gossipmanager.new_gossip_request_arrived, req_data, addr)
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
