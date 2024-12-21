import asyncio
import socket
import struct

from src.avails import Wire, WireData, connect, const, use
from src.core import get_this_remote_peer
from src.core.transfers import REQUESTS_HEADERS

DISCOVER_RETRIES = 3
DISCOVER_TIMEOUT = 3


async def broadcast_search(broadcast_addr, req_payload):
    loop = asyncio.get_event_loop()
    with connect.UDPProtocol.create_async_server_sock(
            loop,
            broadcast_addr
    ) as broadcast_sock:
        broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        task = asyncio.create_task(wait_for_replies(broadcast_sock, DISCOVER_TIMEOUT))
        return await _waiter_loop(("<broadcast>", broadcast_addr[1]),broadcast_sock,req_payload, task)


async def multicast_search(multicast_addr, req_payload):
    loop = asyncio.get_event_loop()
    with connect.UDPProtocol.create_async_server_sock(
            loop,
            multicast_addr
    ) as multicast_sock:
        multicast_sock.setsockopt(socket.IPPROTO_IP,
                                  socket.IP_MULTICAST_TTL, 2)

        # TODO: This should only be used if we do not have inproc method!
        multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        group = socket.inet_aton("{0}".format(multicast_addr))
        mreq = struct.pack('4sl', group, socket.INADDR_ANY)
        multicast_sock.setsockopt(socket.SOL_IP,
                                  socket.IP_ADD_MEMBERSHIP, mreq)

        task = asyncio.create_task(wait_for_replies(multicast_sock, DISCOVER_TIMEOUT))

        return await _waiter_loop(multicast_addr, multicast_sock, req_payload, task)


def _waiter_loop(addr, sock, req_payload, task):
    async for _ in use.async_timeouts(max_retries=DISCOVER_RETRIES):
        Wire.send_datagram(sock, addr, bytes(req_payload))
        if task.done():
            break
    return task


async def search_network():
    ip, port = const.THIS_IP, const.PORT_REQ
    this_id = get_this_remote_peer().id
    ping_data = WireData(REQUESTS_HEADERS.NETWORK_FIND, this_id)
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
        if data.match_header(REQUESTS_HEADERS.NETWORK_FIND_REPLY):
            print("reply detected")  # debug
            print("got some data", data)  # debug
            return tuple(data['connect_uri'])
