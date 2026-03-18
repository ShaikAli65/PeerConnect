import asyncio
import inspect
import logging
import sys

from src.avails import const
from src.avails.mixins import Dispatcher
from src.core import _kademlia, gossip
from src.core.app import AppType, provide_app_ctx
from src.core.discover import discovery_initiate
from src.net import requests
from src.net.events import RequestEvent
from src.net.transports import RequestsTransport
from src.transfers import REQUESTS_HEADERS

_logger = logging.getLogger(__name__)


async def initiate(app: AppType):

    req_dispatcher = RequestsDispatcher()
    await app.exit_stack.enter_async_context(req_dispatcher)
    multicast_address = (const.MULTICAST_IP_v4 if const.USING_IP_V4 else const.MULTICAST_IP_v6,
                         const.PORT_NETWORK)

    dgram_transport, req_transport = await _make_req_endpoint(
        req_dispatcher,
        multicast_address,
        app.addr_tuple,
        app.this_ip,
        app.finalizing,
    )

    kad_server = await _kademlia.prepare_kad_server(
        dgram_transport,
        app.peer_list,
        app.in_network,
        app.addr_tuple,
        app.this_remote_peer,
        app.exit_stack,
    )

    _kademlia.register_into_dispatcher(kad_server, req_dispatcher)

    gossip_transport, g_dispatcher, gossiper = await gossip.initiate_gossip(
        dgram_transport,
        req_dispatcher,
        app.peer_list,
        app.exit_stack,
    )
    app.gossip.transport = gossip_transport
    app.gossip.gossiper = gossiper
    app.gossip.dispatcher = g_dispatcher

    _logger.info("joined gossip network")

    app.requests.dispatcher = req_dispatcher
    app.requests.transport = req_transport
    app.kad_server = kad_server

    discovery_transport, discover_dispatcher = await discovery_initiate(
        multicast_address,
        app.exit_stack,
        req_dispatcher,
        app.addr_tuple,
        app.this_ip,
        app.this_remote_peer,
        kad_server,
        app.in_network,
        app.finalizing,
        dgram_transport
    )

    app.discovery.dispatcher = discover_dispatcher
    app.discovery.transport = discovery_transport

    # TODO: who is the owner of this task??
    await asyncio.create_task(kad_server.add_this_peer_to_lists())


async def _make_req_endpoint(req_dispatcher, multicast_address, addr_tuple_gen, this_ip, finalizing_event):

    try:
        transport = await requests.setup_endpoint(
            requests.get_bind_address(this_ip, addr_tuple_gen),
            multicast_address,
            req_dispatcher,
            finalizing_event,
            addr_tuple_gen,
        )
        _logger.debug("created requests transport")
    except OSError as oe:
        print(const.BIND_FAILED_MSG, file=sys.stderr)
        _logger.critical("failed to bind acceptor", exc_info=True)
        raise RuntimeError from oe

    rt = req_dispatcher.transport = RequestsTransport(transport)
    return transport, rt


class RequestsDispatcher(*Dispatcher):
    __slots__ = 'transport'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry[REQUESTS_HEADERS.REQUEST] = {}
        # for simple handlers

    async def submit(self, req_event: RequestEvent):

        if self.is_registered(req_event.request):
            self.reply_arrived(req_event.request)
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


@provide_app_ctx
async def end_requests(app_ctx):
    app_ctx.kademlia_network_server.stop()
    app_ctx.requests_transport.close()
