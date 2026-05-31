import asyncio
import functools
import socket
from asyncio import shield
from itertools import count
from logging import getLogger

from kademlia.storage import ForgetfulStorage
from net import REQUESTS_FLAG, RequestsTransport
from src.avails import const
from src.net import UDPProtocol, ipv4_multicast_socket_helper, ipv6_multicast_socket_helper, unpack_datagram
from src.net.connect import Interface
from src.net.events import RequestEvent

_logger = getLogger(__name__)


class RequestsEndPoint(asyncio.DatagramProtocol):

    def __init__(self, dispatcher, finalizing_event, interface: Interface):
        """A Requests Endpoint

            Handles all the requests/messages come to the application's requests endpoint
            separates messages related to kademila and calls respective callbacks that are supposed to be called

            Args:
                dispatcher(RequestsDispatcher) : dispatcher object that gets `called` when a datagram arrives
        """

        self.transport = None
        self.requests_transport = None
        self.dispatcher = dispatcher
        self._finalizing_event = finalizing_event
        self.interface = interface
        # we only keep ack futures for ACK_FUTURES_TTL seconds
        self._ack_futs = ForgetfulStorage(const.ACK_FUTURES_TTL)  # msg_id -> asyncio.Future
        self._prune_ack_futs()
        self.ack_id_counter = count()

    def _prune_ack_futs(self, *args, **kwargs):
        self._ack_futs.cull()
        loop = asyncio.get_running_loop()
        loop.call_later(const.ACK_FUTURES_TTL, self._prune_ack_futs)

    def connection_made(self, transport):
        self.transport = transport
        self.requests_transport = RequestsTransport(transport)
        _logger.info(f"started requests endpoint at {transport.get_extra_info('socket')}")

    async def wait_for_ack(self, msg_id, timeout):
        f = self._ack_futs[msg_id] = asyncio.get_running_loop().create_future()
        return await asyncio.wait_for(shield(f), timeout=timeout)

    def datagram_received(self, actual_data, addr):
        if self._finalizing_event.is_set():
            _logger.warning(f"application is finalizing, ignoring request packet from: {addr}")
            return

        code, req_data = self._decode_packet(actual_data, addr)
        if code is None:  # this means the packet does not require further processing
            return

        event = RequestEvent(root_code=code, request=req_data,
                             from_addr=self.interface.addr_tuple(port=addr[1], ip=addr[0]))
        self.dispatcher(event)

    def _decode_packet(self, actual_data, addr):
        code, data = actual_data[:REQUESTS_FLAG.max_byte_len], actual_data[REQUESTS_FLAG.max_byte_len:]
        code = REQUESTS_FLAG.bytes_to_flag(code)
        base_flag = REQUESTS_FLAG(code & (REQUESTS_FLAG.EXTRA - 1))
        extra_flags = REQUESTS_FLAG(code & ~(REQUESTS_FLAG.EXTRA - 1))

        if extra_flags & REQUESTS_FLAG.ACK:
            try:
                fut = self._ack_futs[data]
            except KeyError:
                _logger.warning(f"received ack for unknown message id: {data}")
                return None, None

            if not fut.done():
                fut.set_result(None)

            return None, None

        req_data = unpack_datagram(data)
        if extra_flags & REQUESTS_FLAG.REQUIRE_ACK:
            self.requests_transport.sendto(req_data.msg_id.encode(), addr, extra_flags=REQUESTS_FLAG.ACK)
            _logger.debug(f"received request to send ack, acking {req_data.msg_id=}")

        return base_flag, req_data

    def error_received(self, exc):
        _logger.error(f"error received: {exc}")


def get_bind_address(port_req, interface: Interface):
    if const.IS_WINDOWS:
        # a discovery request packet is observed in wire shark but that packet is
        # not getting delivered to application socket in linux when we bind to specific interface address

        # TL;DR: causing some unknown behaviour in linux system
        const.BIND_IP = interface.ip
    return interface.addr_tuple(port=port_req, ip=const.BIND_IP)


async def setup_endpoint(
      bind_address, multicast_address, req_dispatcher, finalizing_event, interface: Interface
) -> tuple[asyncio.DatagramProtocol, RequestsEndPoint]:
    assert isinstance(bind_address, tuple) and isinstance(multicast_address,
                                                          tuple), "expecting bind_address and multicast_address"
    loop = asyncio.get_running_loop()

    base_socket = UDPProtocol.create_async_server_sock(
        loop, bind_address, family=const.IP_VERSION
    )

    _subscribe_to_multicast(base_socket, multicast_address)
    base_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return await loop.create_datagram_endpoint(  # noqa
        functools.partial(RequestsEndPoint, req_dispatcher, finalizing_event, interface),
        sock=base_socket
    )


def _subscribe_to_multicast(sock, multicast_addr):
    if const.USING_IP_V4:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        log = "registered request socket for broadcast"
        if not sock.getsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST):
            log = "not " + log
        _logger.debug(log)

        ipv4_multicast_socket_helper(
            sock,
            sock.getsockname(),
            multicast_addr,
            logger=_logger
        )
        _logger.debug(f"registered request socket for multicast v4 {multicast_addr}")
    else:
        ipv6_multicast_socket_helper(
            sock,
            multicast_addr,
            logger=_logger
        )
        _logger.debug(f"registered request socket for multicast v6 {multicast_addr}")
    return sock
