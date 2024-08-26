import struct
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
from src.core import get_this_remote_peer, discover, REQUESTS

from typing import Union, Dict, Tuple
from src.avails import const


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
        data = data.decode()
        print("Received:", data, "from", addr)  # debug
        if data == REQUESTS.NETWORK_FIND:
            this_rp = get_this_remote_peer()
            header = REQUESTS.NETWORK_FIND_REPLY
            connect_uri = pickle.dumps(this_rp.network_uri)
            payload_len = struct.pack('!I', len(connect_uri))
            data_payload = header + payload_len + connect_uri
            print("sending data", data_payload)  # debug
            self.transport.sendto(data_payload, addr)
            self.transport.close()

    def connection_made(self, transport):
        self.transport = transport
        print("Connection made", self.transport)  # debug


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
    print('started requests endpoint at', this_rp.req_uri)  # debug
