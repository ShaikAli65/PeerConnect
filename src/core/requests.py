import asyncio
import logging
import socket

import umsgpack

from src.avails import Wire, WireData, connect, const, use
from src.core import Dock, get_this_remote_peer
from . import discover, gossip

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)

# :todo: write consensus protocol for replying a network find request


class RequestsEndPoint(asyncio.DatagramProtocol):

    def datagram_received(self, data_payload, addr):
        try:
            data = Wire.load_datagram(data_payload)
            req_data = WireData.load_from(data)
        except umsgpack.UnpackException as ue:
            print('data illformed:', ue, data_payload)
            return

        print("Received:", req_data, "from", addr)  # debug
        if req_data.match_header(REQUESTS.NETWORK_FIND):
            this_rp = get_this_remote_peer()
            data_payload = WireData(header=REQUESTS.NETWORK_FIND_REPLY, _id=None, connect_uri=this_rp.network_uri)
            self.transport.sendto(bytes(data_payload), addr)
            print("sending as reply", data_payload)  # debug
        elif req_data.match_header(REQUESTS.NETWORK_FIND_REPLY):
            bootstrap_node_addr = req_data['connect_uri']
            Dock.kademlia_network_server.bootstrap([bootstrap_node_addr])
        elif req_data.match_header(REQUESTS.GOSSIP_MESSAGE):
            gossip_protocol = gossip.get_gossip()
            gossip_protocol.message_arrived(req_data)

    def connection_made(self, transport):
        self.transport = transport
        print("Connection made", self.transport)  # debug


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
    await server.listen(port=const.PORT_NETWORK)

    node_addr = await search_network()
    if node_addr is not None:
        print('bootstrapping kademlia with', node_addr)  # debug
        if await server.bootstrap([node_addr,]):
            Dock.server_in_network = True

    transport, proto = await loop.create_datagram_endpoint(
        RequestsEndPoint,
        local_addr=('0.0.0.0', const.PORT_REQ),
        family=const.IP_VERSION,
        proto=socket.IPPROTO_UDP,
        allow_broadcast=True,
    )

    Dock.protocol = proto
    Dock.requests_endpoint = transport
    Dock.kademlia_network_server = server
    print('started requests endpoint at', transport.get_extra_info('socket'))  # debug
    await server.add_this_peer_to_lists()
    await gossip.join_gossip(server)
    print('added this peer object')  # debug
    return server, transport, proto


async def search_network():
    ip, port = const.THIS_IP, const.PORT_REQ
    print(ip,port)
    this_id = get_this_remote_peer().id
    ping_data = WireData(REQUESTS.NETWORK_FIND, this_id)
    s = connect.UDPProtocol.create_async_server_sock(
        asyncio.get_running_loop(),
        (ip, port),
        family=const.IP_VERSION
    )
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    with s:
        await ping_network(s, port, ping_data)
        print('sent broadcast to network at port', ip, port)  # debug
        return await wait_for_replies(s)


async def ping_network(sock, port, req_payload, *, times=4):
    for delay in use.get_timeouts(max_retries=times):
        Wire.send_datagram(sock, ('<broadcast>', port), bytes(req_payload))
        print("sent broadcast")  # debug
        await asyncio.sleep(delay)


async def wait_for_replies(sock, timeout=6):
    print("waiting for replies at", sock)
    while True:
        try:
            raw_data, addr = await asyncio.wait_for(Wire.recv_datagram_async(sock), timeout)
        except asyncio.TimeoutError:
            print(f'timeout reached at {use.func_str(wait_for_replies)}')
            return None
        data = WireData.load_from(raw_data)
        print("some data came ", data)  # debug
        if addr == sock.getsockname():
            print('ignoring echo')  # debug
            continue
        if data.match_header(REQUESTS.NETWORK_FIND_REPLY):
            print("reply detected")  # debug
            print("got some data", data)  # debug
            return data['connect_uri']


async def end_requests():
    Dock.server_in_network = False
    Dock.kademlia_network_server.stop()
    Dock.requests_endpoint.close()
    Dock.requests_endpoint = None

