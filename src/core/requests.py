import asyncio
import inspect
import logging
import sys
from typing import NamedTuple

from src.configurations.appconfig import AppConfig, AppRunTime
from src.net import connectivity, requests
from src import net
from src.avails import const
from src.avails.mixins import Dispatcher
from src.core import _kademlia, gossip
from src.core.discover import discovery_initiate

_logger = logging.getLogger(__name__)


async def _make_req_endpoint(
        req_dispatcher,
        multicast_address,
        port_req,
        interface,
        finalizing_event,
):
    """

    Args:
        req_dispatcher (RequestsDispatcher):
    """
    try:
        transport = await requests.setup_endpoint(
            requests.get_bind_address(port_req, interface),
            multicast_address,
            req_dispatcher,
            finalizing_event,
            interface,
        )
        _logger.debug("created requests transport")
    except OSError as oe:
        print(const.BIND_FAILED_MSG, file=sys.stderr)
        _logger.critical("failed to bind acceptor", exc_info=True)
        raise RuntimeError from oe

    return transport, net.RequestsTransport(transport)


class RequestsDispatcher(*Dispatcher):
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry[net.REQUESTS_HEADERS.REQUEST] = {}

    async def submit(self, req_event: net.RequestEvent):

        if self.is_registered(req_event.request):
            self.reply_arrived(req_event.request)
            return

        # reply registry and dispatcher's registry are most often mutually exclusive
        # going with try except because the hit rate to the self.registry will be high
        # when compared to reply registry
        try:
            if req_event.root_code == net.REQUESTS_HEADERS.REQUEST:
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
            if inspect.isawaitable(f := handler(req_event)):
                await f
        except RuntimeError:
            await self._handle_runtime_error(_logger)
        except Exception as e:
            # we can't afford exceptions here as they move into QueueMixIn
            _logger.error(f"{handler}({req_event}) failed with \n", exc_info=e)

    def register_simple_handler(self, header, handler):
        """Register a simple callback against ``REQUESTS_HEADERS.REQUEST``
        These handlers mostly invoked when a datagram is sent using ``requests_transport``, that has root_code = REQUESTS_HEADERS.REQUEST
        """
        self.registry[net.REQUESTS_HEADERS.REQUEST][header] = handler


class RequestsService(NamedTuple):
    dispatcher: RequestsDispatcher
    transport: net.RequestsTransport


async def initiate(
        this_interface: net.Interface,
        this_remote_peer,
        app_runtime: AppRunTime,
        app_config: AppConfig,
):
    """
    Initializes and orchestrates multiple network services such as request handling,
    Kademlia-based peer-to-peer services, gossip protocols, and discovery mechanisms.

    Args:
        this_interface (net.Interface): The network interface to be used for communication.
        this_remote_peer: The remote peer's details or identifier to establish communication within the network.
        app_runtime (AppRunTime): The runtime context containing the application's lifecycle and resources.
        app_config (AppConfig): The application's configuration, which includes network-specific details
            like request ports.

    Returns:
        tuple: A tuple containing:
            - RequestsService: The request handling service connected to the dispatcher.
            - GossipService: The initialized gossip protocol service.
            - DiscoveryService: The discovery service for network peers.
            - KademliaServer: The Kademlia-based server instance for peer-to-peer networking.
    """

    req_dispatcher = RequestsDispatcher()
    await app_runtime.exit_stack.enter_async_context(req_dispatcher)
    multicast_address = (const.MULTICAST_IP_v4 if const.USING_IP_V4 else const.MULTICAST_IP_v6,
                         const.PORT_NETWORK)

    dgram_transport, req_transport = await _make_req_endpoint(
        req_dispatcher,
        multicast_address,
        app_config.req_port,
        this_interface,
        app_runtime.finalizing,
    )
    requests_service = RequestsService(req_dispatcher, req_transport)

    connectivity_checker = await connectivity.initiate(
        app_runtime.exit_stack,
        requests_service,
        this_remote_peer.peer_id,
    )

    kad_server = await _kademlia.prepare_kad_server(
        dgram_transport,
        app_runtime,
        this_interface,
        this_remote_peer,
        connectivity_checker,
    )

    _kademlia.register_into_dispatcher(kad_server, req_dispatcher)

    gossip_service, gossip_searcher = await gossip.initiate_gossip(
        dgram_transport,
        this_remote_peer,
        req_dispatcher,
        app_runtime.peer_list,
        app_runtime.exit_stack,
    )

    _logger.info("joined gossip network")

    discovery_service = await discovery_initiate(
        multicast_address,
        app_runtime.exit_stack,
        req_dispatcher,
        this_interface,
        this_remote_peer,
        kad_server,
        app_runtime.in_network,
        app_runtime.finalizing,
        dgram_transport
    )

    # this task is internally managed by KademliaServer
    await asyncio.create_task(kad_server.add_this_peer_to_lists())

    return requests_service, gossip_service, gossip_searcher, discovery_service, kad_server, connectivity_checker
