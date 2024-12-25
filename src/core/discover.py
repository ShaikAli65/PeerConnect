import asyncio
import socket
from typing import Literal

from src.avails import Wire, WireData, const, use
from src.avails.connect import UDPProtocol, ipv4_multicast_socket_helper, ipv6_multicast_socket_helper
from src.core import get_this_remote_peer
from src.core.transfers import REQUESTS_HEADERS


async def search_network(bind_addr, broad_cast_addr, multicast_addr):
    """

    """

    this_id = get_this_remote_peer().id
    ping_data = WireData(REQUESTS_HEADERS.NETWORK_FIND, this_id)
    const.BIND_IP = const.THIS_IP
    loop = asyncio.get_event_loop()

    with UDPProtocol.create_async_server_sock(
            loop,
            bind_addr,
            family=const.IP_VERSION
    ) as common_sock:
        common_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        replies = []
        if const.USING_IP_V4:
            broad_cast_responses = await broadcast_search(common_sock, broad_cast_addr, ping_data)
            replies.append(broad_cast_responses)

        multicast_responses = await multicast_search(common_sock, multicast_addr, ping_data)
        replies.append(multicast_responses)
        return replies


async def broadcast_search(broadcast_sock, broadcast_addr: tuple[Literal['<broadcast>'] | str, int], req_payload):
    broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    f = _request_response_loop(
        broadcast_sock,
        broadcast_addr,
        req_payload,
        const.DISCOVER_RETRIES
    )
    answer = await f
    broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 0)
    return answer


async def _request_response_loop(sock, send_addr, req_payload, retry_count):
    reply_fut = asyncio.get_event_loop().create_future()

    async def _reply_waiter():

        def is_a_valid_response(_reply, _addr):
            if _addr == sock.getsockname():
                print('ignoring echo')  # debug
                return False
            if _reply.match_header(REQUESTS_HEADERS.NETWORK_FIND_REPLY):
                return True

        print("listening for discover replies on", sock.getsockname())
        while True:
            raw_data, addr = await Wire.recv_datagram_async(sock)
            reply = WireData.load_from(raw_data)
            print("got", reply, addr)
            if is_a_valid_response(reply, addr):
                print("reply detected", reply)  # debug
                result = tuple(reply['connect_uri'])
                reply_fut.set_result(result)  # we got address to bootstrap with
                return result

    task = asyncio.create_task(_reply_waiter())

    for timeout in use.get_timeouts(max_retries=retry_count):
        Wire.send_datagram(sock, send_addr, bytes(req_payload))
        print(f"sent{send_addr}" + ("=" * 80))
        try:
            resp = await asyncio.wait_for(asyncio.shield(reply_fut), timeout)
            print("got" + '=>', resp)
            task.cancel()
            return resp
        except TimeoutError:
            print("timeout")

    task.cancel()


async def multicast_search(multicast_sock, multicast_addr, req_payload):
    if const.USING_IP_V4:
        ipv4_multicast_socket_helper(multicast_sock, multicast_addr)
    else:
        ipv6_multicast_socket_helper(multicast_sock, multicast_addr)

    answer = await _request_response_loop(
        multicast_sock,
        multicast_addr,
        req_payload,
        const.DISCOVER_RETRIES
    )
    return answer
