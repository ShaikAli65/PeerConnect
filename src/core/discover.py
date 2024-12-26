import asyncio
import socket
from typing import Literal

from src.avails import QueueMixIn, Wire, WireData, const, use
from src.avails.bases import BaseDispatcher, RequestEvent
from src.avails.connect import ipv4_multicast_socket_helper, ipv6_multicast_socket_helper
from src.core import get_this_remote_peer
from src.core.transfers import REQUESTS_HEADERS
from src.core.transfers.transports import DiscoveryTransport


class DiscoveryDispatcher(QueueMixIn, BaseDispatcher):
    def __init__(self, transport, stopping_flag):
        self.registry = {
            REQUESTS_HEADERS.NETWORK_FIND: self.find_request,
        }
        super().__init__(transport=DiscoveryTransport(transport), stop_flag=stopping_flag)

    async def submit(self, event: RequestEvent):
        wire_data = WireData.load_from(event.request)  # we need to extract data as request dispatcher
        handle = self.registry[wire_data.header]
        await handle(wire_data)

    async def find_request(self, req_packet: WireData):
        print("replying to ", req_packet.body)
        this_rp = get_this_remote_peer()
        data_payload = WireData(
            header=REQUESTS_HEADERS.NETWORK_FIND_REPLY,
            _id=this_rp.id,
            connect_uri=this_rp.req_uri
        )
        return self.transport.sendto(bytes(data_payload), tuple(req_packet['reply_addr']))


async def search_network(transport, broad_cast_addr, multicast_addr):
    this_rp = get_this_remote_peer()
    ping_data = WireData(REQUESTS_HEADERS.NETWORK_FIND, this_rp.id, reply_addr=this_rp.req_uri)

    if const.USING_IP_V4:
        async for _ in use.async_timeouts(const.DISCOVER_RETRIES):
            transport.sendto(bytes(ping_data), broad_cast_addr)

    async for _ in use.async_timeouts(const.DISCOVER_RETRIES):
        transport.sendto(bytes(ping_data), multicast_addr)


def _add_broadcast(sock):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)


def _add_multicast(multicast_sock, addr):
    if const.USING_IP_V4:
        ipv4_multicast_socket_helper(multicast_sock, addr)
    else:
        ipv6_multicast_socket_helper(multicast_sock, addr)


@use.NotInUse
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


@use.NotInUse
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
            return resp
        except TimeoutError:
            print("timeout")

    task.cancel()


@use.NotInUse
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
