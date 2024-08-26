import threading
import socket
import time
import json
import asyncio
import os
import pickle

from src.avails import DataWeaver, SimplePeerBytes, RemotePeer
from src.avails import connect
from kademlia import protocol, network, routing
from src.core import peer_list, get_this_remote_peer,set_current_remote_peer_object, discover


from typing import Union, Dict, Tuple
from src.avails import const


class RequestProtocol(protocol.KademliaProtocol):
    def __init__(self, source_node, storage, ksize):
        super().__init__(source_node, storage, ksize)

    def rpc_gossip(self, sender, nodeid, message):
        print('got message from ', nodeid, message)
        if message['ttl'] == 0:
            return
        message['ttl'] -= 1
        self.call_gossip(message)

    async def call_gossip(self, message):
        for node in routing.TableTraverser(self.router, self.source_node):
            print('sending gossip message', node)
            address = (node.ip, node.port)
            await self.gossip(address, self.source_node.id, message)


class EndPoint(asyncio.DatagramProtocol):

    def datagram_received(self, data, addr):
        print("Received:", data.decode())

        this_rp = get_this_remote_peer()
        self.transport.sendto(pickle.dumps(this_rp.network_uri), addr)
        self.transport.close()

    def connection_made(self, transport):
        self.transport = transport
        print("Connection made", self.transport)


async def initiate():
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
    print('started requests endpoint')  # debug
