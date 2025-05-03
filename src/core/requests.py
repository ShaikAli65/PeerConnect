import inspect
import logging

from src.avails import const
from src.avails.bases import BaseDispatcher
from src.avails.mixins import QueueMixIn, ReplyRegistryMixIn
from src.core import _kademlia, gossip
from src.core.app import AppType, provide_app_ctx
from src.core.discover import discovery_initiate
from src.core.events import RequestEvent
from src.managers.statemanager import State
from src.net.requests import setup_endpoint
from src.net.transports import RequestsTransport
from src.transfers import REQUESTS_HEADERS

_logger = logging.getLogger(__name__)


async def initiate(app: AppType):
    if const.IS_WINDOWS:
        # a discovery request packet is observed in wire shark but that packet is
        # not getting delivered to application socket in linux when we bind to specific interface address

        # TL;DR: causing some unknown behaviour in linux system
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
        print(const.BIND_FAILED_MSG)
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


class RequestsDispatcher(QueueMixIn, ReplyRegistryMixIn, BaseDispatcher):
    __slots__ = ()

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
