import asyncio
import functools
import socket
from logging import getLogger

from src.avails import const
from src.avails.exceptions import InvalidPacket
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
        self.dispatcher = dispatcher
        self._finalizing_event = finalizing_event
        self.interface = interface

    def connection_made(self, transport):
        self.transport = transport
        _logger.info(f"started requests endpoint at {transport.get_extra_info('socket')}")

    def datagram_received(self, actual_data, addr):
        if self._finalizing_event.is_set():
            _logger.warning(f"application is finalizing, ignoring request packet from: {addr}")
            return
        code, stripped_data = actual_data[:1], actual_data[1:]
        try:
            req_data = unpack_datagram(stripped_data)
        except InvalidPacket as ip:
            _logger.info(f"error:", exc_info=ip)
            return

        event = RequestEvent(root_code=code, request=req_data, from_addr=self.interface.addr_tuple(port=addr[1], ip=addr[0]))
        self.dispatcher(event)


def get_bind_address(port_req, interface: Interface):
    if const.IS_WINDOWS:
        # a discovery request packet is observed in wire shark but that packet is
        # not getting delivered to application socket in linux when we bind to specific interface address

        # TL;DR: causing some unknown behaviour in linux system
        const.BIND_IP = interface.ip
    return interface.addr_tuple(port=port_req, ip=const.BIND_IP)


async def setup_endpoint(bind_address, multicast_address, req_dispatcher, finalizing_event, interface: Interface):
    assert isinstance(bind_address, tuple) and isinstance(multicast_address,
                                                          tuple), "expecting bind_address and multicast_address"
    loop = asyncio.get_running_loop()

    base_socket = UDPProtocol.create_async_server_sock(
        loop, bind_address, family=const.IP_VERSION
    )

    _subscribe_to_multicast(base_socket, multicast_address)
    base_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    transport, _ = await loop.create_datagram_endpoint(
        functools.partial(RequestsEndPoint, req_dispatcher, finalizing_event, interface),
        sock=base_socket
    )
    return transport


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


async def send_request(req_service, msg, peer, *, expect_reply=False):
    """Send a msg to requests endpoint of the peer

    Notes:
        if expect_reply is True and no msg_id available in msg raises InvalidPacket

    Args:
        req_service(RequestService): requests service to use for sending and receiving ack.
        msg(WireData): message to send
        peer(RemotePeer): msg is sent to
        expect_reply(bool): waits until a reply is arrived with the same id as the msg packet

    Raises:
        InvalidPacket: if msg does not contain msg_id and expecting a reply
    """
    # TODO: add retries

    if msg.msg_id is None and expect_reply is True:
        raise InvalidPacket("msg_id not found and expecting a reply")

    req_service.transport.sendto(bytes(msg), peer.req_uri)

    if expect_reply:
        return await req_service.router.register_reply(msg.msg_id)
    return None
