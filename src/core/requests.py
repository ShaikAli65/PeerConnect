import asyncio
import logging
import sys
from typing import NamedTuple

from src import net
from src.avails import BaseDispatcher, Router, const
from src.avails.mixins import CallHandlerMixIn, ReplyRegistryMixIn, TaskGroupMixIn
from src.configurations.appconfig import AppConfig, AppRunTime
from src.core import _kademlia
from src.gossip import app_gossip
from src.core.discover import discovery_initiate
from src.core.user_prompts import UserPrompts
from src.net import requests

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


class RequestsDispatcher(TaskGroupMixIn, ReplyRegistryMixIn, CallHandlerMixIn, BaseDispatcher):
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.req_router = Router()
        self.register_handler(net.REQUESTS_HEADERS.REQUEST, self.req_router)

    async def submit(self, req_event: net.RequestEvent):

        if self.is_registered(req_event.request):
            self.reply_arrived(req_event.request)
            return None

        return await self.call_handler(req_event, _logger=_logger)

    def register_simple_handler(self, header, handler):
        """Register a simple callback against ``REQUESTS_HEADERS.REQUEST``
        These handlers mostly invoked when a datagram is sent using ``requests_transport``, that has root_code = REQUESTS_HEADERS.REQUEST
        """
        self.req_router.register_handler(header, handler)


class RequestsService(NamedTuple):
    dispatcher: RequestsDispatcher
    transport: net.RequestsTransport


async def initiate(
      this_interface: net.Interface,
      this_remote_peer,
      peer_service,
      app_runtime: AppRunTime,
      app_config: AppConfig,
      user_prompts: UserPrompts,
):
    """
    Initializes the networking and peer-to-peer communication components
    of the application. Sets up key network services such as message dispatching,
    multicast discovery, Kademlia-based distributed hash table (DHT) server,
    gossip protocol-based network, and peer discovery services.

    Args:
        this_interface (net.Interface): The network interface to be used for communication.
        this_remote_peer: Object representing the remote peer in the network.
        peer_service: Object providing services related to peer management.
        app_runtime (AppRunTime): The runtime context of the application, including shared state
            and utilities for managing lifecycle tasks.
        app_config (AppConfig): The application configuration containing network setup details.

    Returns:
        tuple: A tuple consisting of the following services:
            - requests_service (RequestsService): Service for handling network requests.
            - gossip_service: Service for managing gossip protocol operations.
            - gossip_searcher: Object for executing search logic using gossip.
            - discovery_service: Service for discovering peers in the network.
            - kad_server (KademliaServer): Instance of the Kademlia server for decentralized storage.

    """

    req_dispatcher = RequestsDispatcher()
    await app_runtime.exit_stack.enter_async_context(req_dispatcher)

    multicast_address = (
        const.MULTICAST_IP_v4 if const.USING_IP_V4 else const.MULTICAST_IP_v6,
        const.PORT_NETWORK
    )

    dgram_transport, req_transport = await _make_req_endpoint(
        req_dispatcher,
        multicast_address,
        app_config.req_port,
        this_interface,
        app_runtime.finalizing,
    )
    requests_service = RequestsService(req_dispatcher, req_transport)

    kad_server = await _kademlia.prepare_kad_server(
        dgram_transport,
        app_runtime,
        this_interface,
        this_remote_peer,
        peer_service,
    )

    _kademlia.register_into_dispatcher(kad_server, req_dispatcher)

    gossip_service, gossip_searcher = await app_gossip.initiate_gossip(
        dgram_transport,
        this_remote_peer,
        req_dispatcher,
        app_runtime.peer_list,
    )

    _logger.info("joined gossip network")

    discovery_service = await discovery_initiate(
        multicast_address,
        req_dispatcher,
        this_interface,
        this_remote_peer,
        kad_server,
        app_runtime.in_network,
        app_runtime.finalizing,
        dgram_transport,
        user_prompts,
    )

    # this task is internally managed by KademliaServer
    asyncio.create_task(kad_server.add_this_peer_to_lists())

    return requests_service, gossip_service, gossip_searcher, discovery_service, kad_server
