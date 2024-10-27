import asyncio
import socket

from src.avails import Wire, WireData, connect, const, unpack_datagram, use, wire
from src.core import Dock, get_this_remote_peer, join_gossip
from . import discover, get_gossip, transfers
from ..managers import filemanager, gossipmanager


class RequestsEndPoint(asyncio.DatagramProtocol):

    def datagram_received(self, data_payload, addr):
        req_data = unpack_datagram(data_payload)
        if not req_data:
            return  # Failed to unpack
        print("Received: %s from %s" % (req_data, addr))
        self.handle_request(req_data, addr)

    def handle_request(self, req_data, addr):
        """ Handle different request types based on the header """
        if req_data.match_header(REQUESTS.NETWORK_FIND):
            self.handle_network_find(addr)
        elif req_data.match_header(REQUESTS.NETWORK_FIND_REPLY):
            self.handle_network_find_reply(req_data)
        elif req_data.match_header(REQUESTS.GOSSIP_MESSAGE):
            self.handle_gossip_message(req_data)
        elif req_data.match_header(transfers.HEADERS.GOSSIP_CREATE_SESSION):
            self.handle_gossip_session(req_data, addr)
        elif req_data.match_header(transfers.HEADERS.OTM_FILE_TRANSFER):
            self.handle_onetomanyfile_session(req_data, addr)

    def handle_network_find(self, addr):
        """ Handle NETWORK_FIND request """
        # :todo: write consensus protocol for replying a network find request
        this_rp = get_this_remote_peer()
        data_payload = WireData(
            header=REQUESTS.NETWORK_FIND_REPLY,
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

    def handle_onetomanyfile_session(self, req_data, addr):
        reply = filemanager.new_otm_request_arrived(req_data, addr)
        Wire.send_datagram(self.transport, addr, reply)

    def connection_made(self, transport):
        self.transport = transport
        print('started requests endpoint at', transport.get_extra_info('socket'))  # debug


class REQUESTS:
    __slots__ = ()
    REDIRECT = b'redirect        '
    LIST_SYNC = b'sync list       '
    ACTIVE_PING = b'Y face like that'
    REQ_FOR_LIST = b'list of users  '
    I_AM_ACTIVE = b'com notify user'
    NETWORK_FIND = b'network find    '
    NETWORK_FIND_REPLY = b'networkfindreply'
    GOSSIP_MESSAGE = b'gossip message'


async def initiate():
    loop = asyncio.get_running_loop()
    server = discover.get_new_kademlia_server()
    await server.listen(port=const.PORT_NETWORK, interface=const.THIS_IP)
    print("started kademlia endpoint at ", const.PORT_NETWORK)

    node_addr = await search_network()
    if node_addr is not None:
        print('bootstrapping kademlia with', node_addr)  # debug
        if await server.bootstrap([node_addr,]):
            Dock.server_in_network = True

    transport, proto = await loop.create_datagram_endpoint(
        RequestsEndPoint,
        # local_addr=('0.0.0.0' if const.IP_VERSION == socket.AF_INET else '::', const.PORT_REQ),
        local_addr=(const.THIS_IP, const.PORT_REQ),
        family=const.IP_VERSION,
        proto=socket.IPPROTO_UDP,
        allow_broadcast=True,
    )

    # print("asdasdasd", transport.sendto(b'124',('127.0.0.1', 12002)))
    join_gossip(transport)

    Dock.protocol = proto
    Dock.requests_endpoint = transport
    Dock.kademlia_network_server = server
    f = use.wrap_with_tryexcept(server.add_this_peer_to_lists)
    asyncio.create_task(f())
    return server, transport, proto


async def search_network():
    ip, port = const.THIS_IP, const.PORT_REQ
    this_id = get_this_remote_peer().id
    ping_data = WireData(REQUESTS.NETWORK_FIND, this_id)
    s = connect.UDPProtocol.create_async_server_sock(
        asyncio.get_running_loop(),
        (ip, port),
        family=const.IP_VERSION
    )
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    with s:
        await ping_network(s, port, ping_data, times=2)  # debug
        print('sent broadcast to network at port', ip, port)  # debug
        return await wait_for_replies(s)


async def ping_network(sock, port, req_payload, *, times=4):
    for delay in use.get_timeouts(max_retries=times):
        Wire.send_datagram(sock, ('<broadcast>', port), bytes(req_payload))
        print("sent broadcast")  # debug
        await asyncio.sleep(delay)


async def wait_for_replies(sock, timeout=3):
    print("waiting for replies at", sock)
    while True:
        try:
            raw_data, addr = await asyncio.wait_for(Wire.recv_datagram_async(sock), timeout)
        except asyncio.TimeoutError:
            print(f'timeout reached at {use.func_str(wait_for_replies)}')
            return None
        try:
            data = WireData.load_from(raw_data)
            print("some data came ", data)  # debug
        except TypeError as tp:
            print(f"got error at {use.func_str(wait_for_replies)}", tp)
            return
        if addr == sock.getsockname():
            print('ignoring echo')  # debug
            continue
        if data.match_header(REQUESTS.NETWORK_FIND_REPLY):
            print("reply detected")  # debug
            print("got some data", data)  # debug
            return tuple(data['connect_uri'])


async def end_requests():
    Dock.server_in_network = False
    Dock.kademlia_network_server.stop()
    Dock.requests_endpoint.close()
    Dock.requests_endpoint = None
