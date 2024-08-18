import asyncio
import socket
import threading

import kademlia.routing
import kademlia.network
import kademlia.protocol
from ..avails import connect, const, use


def ping_all(port, *, times=5):
    s = connect.UDPProtocol.create_sync_sock(const.IP_VERSION)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for _ in range(times):
        s.sendto(const.ACTIVE_PING, ('<broadcast>', port))


async def wait_for_replies(ip, port, timeout=5):
    sock = connect.UDPProtocol.create_async_sock(asyncio.get_running_loop(), const.IP_VERSION)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((ip, port))
    sock.settimeout(timeout)
    try:
        data = await sock.arecvfrom(16)
        print(data)
        return data
    except TimeoutError:
        use.echo_print(f"Time Out Reached at {use.func_str(wait_for_replies)}")


async def search_network():
    ip,port = const.THIS_IP, const.PORT_NETWORK
    task = asyncio.create_task(wait_for_replies(ip, port))
    ping_all(port)
    return await task


def initiate_routing():
    kademlia.protocol.RPCProtocol()
    server = kademlia.network.Server()

    ...
