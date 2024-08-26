import asyncio
import pickle
import socket
import struct

import kademlia.protocol
import kademlia.routing

from .requests import REQUESTS
from ..avails import connect, const, use, WireData


class CustomKademliaProtocol(kademlia.protocol.KademliaProtocol):

    ...


def ping_all(sock, port, *, times=3):

    for _ in range(times):
        sock.sendto(REQUESTS.NETWORK_FIND, ('<broadcast>', port))
        print("sent ", _, "time")


async def wait_for_replies(sock, timeout=5):
    print("waiting for replies at", sock)
    while True:
        try:
            data, ipaddr = await asyncio.wait_for(sock.arecvfrom(16), timeout=timeout)
            print("some data came ", data, ipaddr)
            if ipaddr == sock.getsockname():
                continue
            try:
                if data == REQUESTS.NETWORK_FIND_REPLY:
                    print("reply detected")
                    data = await asyncio.wait_for(WireData.receive(sock), timeout)
                    print("got some data", data)
            except (pickle.PickleError, pickle.PicklingError, pickle.UnpicklingError):
                return None
        except asyncio.TimeoutError:
            return None


async def search_network():
    ip, port = const.THIS_IP, const.PORT_REQ
    print(ip,port)
    s = connect.UDPProtocol.create_async_sock(asyncio.get_running_loop(), const.IP_VERSION)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((ip, port))
    with s:
        ping_all(s, port)
        print('sent broadcast to network')
        return await wait_for_replies(s)
