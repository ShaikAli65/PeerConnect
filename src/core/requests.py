import asyncio
import pickle
import socket
import struct

from kademlia import protocol, network, routing

from src.avails import const
from src.core import get_this_remote_peer


class RequestProtocol(protocol.KademliaProtocol):
    def __init__(self, source_node, storage, ksize):
        super().__init__(source_node, storage, ksize)

    def rpc_gossip(self, sender, nodeid, message):
        print('got message from ', nodeid, message)  # debug
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
        print("Received:", data, "from", addr)  # debug
        if data == REQUESTS.NETWORK_FIND:
            this_rp = get_this_remote_peer()
            header = REQUESTS.NETWORK_FIND_REPLY
            connect_uri = pickle.dumps(this_rp.network_uri)
            payload_len = struct.pack('!I', len(connect_uri))
            data_payload = header + payload_len + connect_uri
            print("sending data", data_payload, "to", addr)  # debug
            self.transport.sendto(data_payload, addr)
            self.transport.close()

    def connection_made(self, transport):
        self.transport = transport
        print("Connection made", self.transport)  # debug


async def initiate():
    from . import discover
    loop = asyncio.get_running_loop()
    this_rp = get_this_remote_peer()

    server = network.Server()
    server.protocol_class = RequestProtocol
    await server.listen(*this_rp.network_uri[::-1])

    node_addr = await discover.search_network()
    if node_addr is not None:
        print('bootstrapping kademlia with', node_addr)  # debug
        await server.bootstrap_node(node_addr)

    transport, proto = await loop.create_datagram_endpoint(
        EndPoint,
        local_addr=this_rp.req_uri,
        family=const.IP_VERSION,
        proto=socket.IPPROTO_UDP,
        allow_broadcast=True,
    )
    print('started requests endpoint at', this_rp.req_uri)  # debug


class REQUESTS:
    __slots__ = ()
    REDIRECT = b'redirect        '
    LIST_SYNC = b'sync list       '
    ACTIVE_PING = b'Y face like that'
    REQ_FOR_LIST = b'list of users  '
    I_AM_ACTIVE = b'com notify user'
    NETWORK_FIND = b'network find    '
    NETWORK_FIND_REPLY = b'network find reply '
