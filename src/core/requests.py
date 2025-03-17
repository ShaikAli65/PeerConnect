import asyncio
import functools
import inspect
import logging
import socket

from src.avails import InvalidPacket, WireData, const, unpack_datagram
from src.avails.bases import BaseDispatcher
from src.avails.connect import UDPProtocol, ipv4_multicast_socket_helper, ipv6_multicast_socket_helper
from src.avails.events import RequestEvent
from src.avails.mixins import QueueMixIn, ReplyRegistryMixIn
from src.core import _kademlia, gossip
from src.core.app import AppType, ReadOnlyAppType, provide_app_ctx
from src.core.discover import discovery_initiate
from src.managers.statemanager import State
from src.transfers import REQUESTS_HEADERS
from src.transfers.transports import RequestsTransport

_logger = logging.getLogger(__name__)


async def initiate(app: AppType):
    # a discovery request packet is observed in wire shark but that packet is
    # not getting delivered to application socket in linux when we bind to specific interface address

    # TL;DR: causing some unknown behaviour in linux system

    if const.IS_WINDOWS:
        const.BIND_IP = app.this_ip.ip

    bind_address = app.addr_tuple(port=const.PORT_REQ, ip=const.BIND_IP)

    multicast_address = (const.MULTICAST_IP_v4 if const.USING_IP_V4 else const.MULTICAST_IP_v6, const.PORT_NETWORK)

    req_dispatcher = RequestsDispatcher()
    await app.exit_stack.enter_async_context(req_dispatcher)
    try:
        transport = await setup_endpoint(
            bind_address,
            multicast_address,
            req_dispatcher,
            app.read_only(),
        )
        _logger.debug("created requests transport")
    except OSError as oe:
        print(const.BIND_FAILED)
        _logger.critical("failed to bind acceptor", exc_info=True)
        raise RuntimeError from oe

    req_dispatcher.transport = RequestsTransport(transport)

    kad_server = await _kademlia.prepare_kad_server(transport, app_ctx=app.read_only())
    _kademlia.register_into_dispatcher(kad_server, req_dispatcher)

    await gossip.initiate_gossip(transport, req_dispatcher, app)
    _logger.info("joined gossip network")

    app.requests.dispatcher = req_dispatcher
    app.requests.transport = req_dispatcher.transport
    app.kad_server = kad_server

    discovery_state = State(
        "discovery",
        discovery_initiate,
        multicast_address,
        app,
        transport,
        is_blocking=True,
    )

    add_to_lists = State(
        "adding this peer to lists",
        kad_server.add_this_peer_to_lists,
        is_blocking=True,
    )

    await app.state_manager_handle.put_state(discovery_state)
    await app.state_manager_handle.put_state(add_to_lists)


async def setup_endpoint(bind_address, multicast_address, req_dispatcher, app_ctx):
    assert isinstance(bind_address, tuple) and isinstance(multicast_address,
                                                          tuple), "expecting bind_address and multicast_address"
    loop = asyncio.get_running_loop()

    base_socket = UDPProtocol.create_async_server_sock(
        loop, bind_address, family=const.IP_VERSION
    )

    _subscribe_to_multicast(base_socket, multicast_address)
    transport, _ = await loop.create_datagram_endpoint(
        functools.partial(RequestsEndPoint, req_dispatcher, app_ctx),
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

        ipv4_multicast_socket_helper(sock, sock.getsockname(), multicast_addr)
        _logger.debug(f"registered request socket for multicast v4 {multicast_addr}")
    else:
        ipv6_multicast_socket_helper(sock, multicast_addr)
        _logger.debug(f"registered request socket for multicast v6 {multicast_addr}")
    return sock


class RequestsDispatcher(QueueMixIn, ReplyRegistryMixIn, BaseDispatcher):
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry[REQUESTS_HEADERS.REQUEST] = {}
        # for simple handlers

    async def submit(self, req_event: RequestEvent):

        if self.is_registered(req_event.request):
            self.msg_arrived(req_event.request)
            return

        # reply registry and dispatcher's registry are most often mutually exclusive
        # going with try except because the hit rate to the self.registry will be high
        # when compared to reply registry
        try:
            if req_event.root_code == REQUESTS_HEADERS.REQUEST:
                handler = self.registry[req_event.root_code][req_event.request.header]
                # a simple handler that is associated with requests root-code
            else:
                handler = self.registry[req_event.root_code]
        except KeyError:
            return

        _logger.debug(f"dispatching request with code: {req_event.root_code} to {handler}")
        # expected type of handlers
        # 1. Dispatcher objects that are coupled with QueueMixIn (sync)
        # 2. Dispatcher objects that are not coupled with QueueMixIn (async)
        # 3. any type of handlers (async)

        try:
            await f if inspect.isawaitable(f := handler(req_event)) else None
        except RuntimeError:
            await self._handle_runtime_error(_logger)
        except Exception as e:
            # we can't afford exceptions here as they move into QueueMixIn
            _logger.error(f"{handler}({req_event}) failed with \n", exc_info=e)

    def register_simple_handler(self, header, handler):
        """Register a simple callback against ``REQUESTS_HEADERS.REQUEST``
        These handlers mostly invoked when a datagram is sent using ``requests_transport``, that has root_code = REQUESTS_HEADERS.REQUEST
        """
        self.registry[REQUESTS_HEADERS.REQUEST][header] = handler


class RequestsEndPoint(asyncio.DatagramProtocol):
    __slots__ = 'transport', 'dispatcher', "_app_ctx"

    def __init__(self, dispatcher, app_ctx):
        """A Requests Endpoint

            Handles all the requests/messages come to the application's requests endpoint
            separates messages related to kademila and calls respective callbacks that are supposed to be called

            Args:
                dispatcher(RequestsDispatcher) : dispatcher object that gets `called` when a datagram arrives
                app_ctx(ReadOnlyAppType): application context object to retrieve addr_tuple
        """

        self.transport = None
        self.dispatcher = dispatcher
        self._app_ctx = app_ctx

    def connection_made(self, transport):
        self.transport = transport
        _logger.info(f"started requests endpoint at {transport.get_extra_info('socket')}")

    def datagram_received(self, actual_data, addr):
        if self._app_ctx.finalizing.is_set():
            _logger.warning(f"application is finalizing, ignoring request packet from: {addr}")
            return
        code, stripped_data = actual_data[:1], actual_data[1:]
        try:
            req_data = unpack_datagram(stripped_data)
        except InvalidPacket as ip:
            _logger.info(f"error:", exc_info=ip)
            return

        event = RequestEvent(root_code=code, request=req_data, from_addr=self._app_ctx.addr_tuple(*addr[:2]))
        self.dispatcher(event)


@provide_app_ctx
async def send_request(msg, peer, *, expect_reply=False, app_ctx=None):
    """Send a msg to requests endpoint of the peer

    Notes:
        if expect_reply is True and no msg_id available in msg raises InvalidPacket
    Args:
        msg(WireData): message to send
        peer(RemotePeer): msg is sent to
        expect_reply(bool): waits until a reply is arrived with the same id as the msg packet
        app_ctx(ReadOnlyAppType): application context to retrieve requests transport

    Raises:
        InvalidPacket: if msg does not contain msg_id and expecting a reply
    """

    if msg.msg_id is None and expect_reply is True:
        raise InvalidPacket("msg_id not found and expecting a reply")

    app_ctx.requests.transport.sendto(bytes(msg), peer.req_uri)

    if expect_reply:
        req_disp = app_ctx.requests.dispatcher
        return await req_disp.register_reply(msg.msg_id)


@provide_app_ctx
async def end_requests(app_ctx):
    app_ctx.kademlia_network_server.stop()
    app_ctx.requests_transport.close()
