import asyncio
import logging
import pickle
import socket

import kademlia.network
from kademlia import protocol, network, routing

from src.avails import const, WireData
from src.core import get_this_remote_peer

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)


class REQUESTS:
    __slots__ = ()
    REDIRECT = b'redirect        '
    LIST_SYNC = b'sync list       '
    ACTIVE_PING = b'Y face like that'
    REQ_FOR_LIST = b'list of users  '
    I_AM_ACTIVE = b'com notify user'
    NETWORK_FIND = b'network find    '
    NETWORK_FIND_REPLY = b'networkfindreply'


class RequestProtocol(protocol.KademliaProtocol):
    def __init__(self, source_node, storage, ksize):
        super().__init__(source_node, storage, ksize)

    def rpc_gossip(self, sender, nodeid, message):
        print('got message from ',sender, nodeid, message)  # debug
        if message['ttl'] == 0:
            return
        message['ttl'] -= 1
        self.call_gossip(message)

    async def call_gossip(self, message):
        for node in routing.TableTraverser(self.router, self.source_node):
            print('sending gossip message', node)  # debug
            address = (node.ip, node.port)
            await self.gossip(address, self.source_node.id, message)


class EndPoint(asyncio.DatagramProtocol):

    def datagram_received(self, data, addr):
        try:
            req_data = WireData.load_from(data)
        except pickle.UnpicklingError as pe:
            print('data illformed:', pe, data)
            return

        print("Received:", req_data, "from", addr)  # debug
        if req_data.match_header(REQUESTS.NETWORK_FIND):
            this_rp = get_this_remote_peer()
            data_payload = WireData(header=REQUESTS.NETWORK_FIND_REPLY, _id=None, connect_uri=this_rp.network_uri)
            data_payload.sendto(self.transport, addr)
            # self.transport.sendto(bytes(data_payload), addr)
            # self.transport.sendto(REQUESTS.NETWORK_FIND_REPLY, addr)
            print("sending as reply", data_payload)  # debug

    def connection_made(self, transport):
        self.transport = transport
        print("Connection made", self.transport)  # debug


async def initiate() -> tuple[kademlia.network.Server, asyncio.DatagramTransport, EndPoint]:
    from . import discover
    loop = asyncio.get_running_loop()

    server = network.Server()
    server.protocol_class = RequestProtocol
    await server.listen(port=const.PORT_NETWORK)

    node_addr = await discover.search_network()
    if node_addr is not None:
        print('bootstrapping kademlia with', node_addr)  # debug
        await server.bootstrap_node(node_addr)

    transport, proto = await loop.create_datagram_endpoint(
        EndPoint,
        local_addr=('0.0.0.0', const.PORT_REQ),
        family=const.IP_VERSION,
        proto=socket.IPPROTO_UDP,
        allow_broadcast=True,
    )
    print('started requests endpoint at', transport.get_extra_info('socket'))  # debug
    return server, transport, proto
