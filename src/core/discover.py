import asyncio
import pickle
import socket

import kademlia.protocol
import kademlia.routing

from .requests import REQUESTS
from ..avails import connect, const, use


class CustomKademliaProtocol(kademlia.protocol.KademliaProtocol):

    ...


def ping_all(sock, port, *, times=3):

    for _ in range(times):
        sock.sendto(REQUESTS.NETWORK_FIND, ('<broadcast>', port))
        print("sent ", _, "time")


async def wait_for_replies(sock, timeout=5):
    while True:
        try:
            data, ipaddr = await asyncio.wait_for(sock.arecvfrom(16), timeout=timeout)
            print("some data came ", data, ipaddr)
            if ipaddr == sock.getsockname():
                continue
            try:
                if data == REQUESTS.NETWORK_FIND_REPLY:
                    data_len = await sock.arecv(4)
                    node_contact_ipaddr = await sock.arecv(data_len)
                    data = pickle.loads(node_contact_ipaddr)
                    print("got an ip", data)
                    return data
            except (pickle.PickleError, pickle.PicklingError, pickle.UnpicklingError):
                return None
        except TimeoutError:
            return use.echo_print(f"Time Out Reached at {use.func_str(wait_for_replies)}")


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
