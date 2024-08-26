import asyncio
import pickle
import socket
import struct

import kademlia.protocol
import kademlia.routing

from . import get_this_remote_peer
from .requests import REQUESTS
from ..avails import connect, const, use, WireData


class CustomKademliaProtocol(kademlia.protocol.KademliaProtocol):

    ...


def ping_all(sock, port, *, times=1):
    this_id = get_this_remote_peer().id
    for _ in range(times):
        req_payload = WireData(REQUESTS.NETWORK_FIND, this_id)
        req_payload.sendto(sock, ('<broadcast>', port))
        print("sent ", _, "time")  # debug


async def wait_for_replies(sock, timeout=5):
    print("waiting for replies at", sock)
    while True:
        try:
            data: tuple[WireData, tuple[str, int]] = await asyncio.wait_for(WireData.receive_datagram(sock), timeout)
            print("some data came ", data)  # debug
            if data[1] == sock.getsockname():
                print('ignoring echo')  # debug
                continue
            if data[0].match_header(REQUESTS.NETWORK_FIND_REPLY):
                print("reply detected")  # debug
                print("got some data", data)  # debug
                return data[0]['connect_uri']
        except asyncio.TimeoutError:
            print(f'timeout reached at {use.func_str(wait_for_replies)}')
            return None


async def search_network():
    ip, port = const.THIS_IP, const.PORT_REQ
    print(ip,port)
    s = connect.UDPProtocol.create_async_sock(asyncio.get_running_loop(), const.IP_VERSION)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((ip, port))
    with s:
        ping_all(s, port)
        print('sent broadcast to network at port', ip, port)  # debug
        return await wait_for_replies(s)
