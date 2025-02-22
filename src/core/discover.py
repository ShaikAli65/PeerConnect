"""
Discovery State Machine
-----------------------

  [ initiate ]
       │
       ▼
  [ Register Handlers ]
       │
       ▼
  [ Send Discovery Requests ]
      (up to const.DISCOVERY_RETRIES, with exponential backoff)
       │
       ▼
  ┌──────────────────────────────────────────────┐
  │  Is server bootstrapped?                     │
  ├──────────────────────────┬───────────────────┤
  │ Yes                      │ No
  │ (return quick to passive)│
  │                          ▼
  │            Enter Passive Mode
  │          (send periodic requests)
  │                 │
  │                 │
  │          Server Bootstrapped? <───────────┐
  ├                ─┬─                        │
  │                 │                         │
  │ Yes             │ No                      │
  │ (continue)      │                         │
  ▼                 ▼                         │
    [ Passive Mode ]                          │
  (Wait DISCOVERY_TIMEOUT seconds) ───────────┘

"""

import asyncio
import logging
import traceback
from typing import TYPE_CHECKING

from src.avails import WireData, const, use
from src.avails.bases import BaseDispatcher
from src.avails.events import RequestEvent
from src.avails.mixins import QueueMixIn, ReplyRegistryMixIn
from src.core import DISPATCHS, Dock, addr_tuple, get_this_remote_peer
from src.transfers import DISCOVERY, REQUESTS_HEADERS
from src.transfers.transports import DiscoveryTransport
from src.webpage_handlers import webpage

_logger = logging.getLogger(__name__)


async def discovery_initiate(
        kad_server,
        multicast_address,
        req_dispatcher,
        transport
):
    discover_dispatcher = DiscoveryDispatcher()
    discovery_transport = DiscoveryTransport(transport)
    await Dock.exit_stack.enter_async_context(discover_dispatcher)
    req_dispatcher.register_handler(REQUESTS_HEADERS.DISCOVERY, discover_dispatcher)
    Dock.dispatchers[DISPATCHS.DISCOVER] = discover_dispatcher

    discovery_reply_handler = DiscoveryReplyHandler(kad_server)
    discovery_req_handler = DiscoveryRequestHandler(discovery_transport)

    discover_dispatcher.register_handler(DISCOVERY.NETWORK_FIND_REPLY, discovery_reply_handler)
    discover_dispatcher.register_handler(DISCOVERY.NETWORK_FIND, discovery_req_handler)

    await send_discovery_requests(
        discovery_transport,
        multicast_address
    )


def DiscoveryReplyHandler(kad_server):
    async def handle(event: RequestEvent):
        if event.from_addr[0] == const.THIS_IP:
            return
        connect_address = tuple(event.request["connect_uri"])
        _logger.debug(f"bootstrapping kademlia {connect_address}")
        if any(await kad_server.bootstrap([connect_address])):
            _logger.debug("bootstrapping completed")

    return handle


def DiscoveryRequestHandler(discovery_transport):
    async def handle(event: RequestEvent):
        req_packet = event.request
        if req_packet["reply_addr"][0] == const.THIS_IP:
            _logger.debug("ignoring echo")
            return
        _logger.info(f"discovery replying to req: {req_packet.body}")
        this_rp = get_this_remote_peer()
        data_payload = WireData(
            header=DISCOVERY.NETWORK_FIND_REPLY,
            msg_id=this_rp.peer_id,
            connect_uri=this_rp.req_uri[:2],
        )
        discovery_transport.sendto(
            bytes(data_payload), addr_tuple(*req_packet["reply_addr"][:2])
        )

    return handle


class DiscoveryDispatcher(QueueMixIn, ReplyRegistryMixIn, BaseDispatcher):
    __slots__ = ()
    if TYPE_CHECKING:
        transport: DiscoveryTransport

    async def submit(self, event: RequestEvent):
        wire_data = event.request
        self.msg_arrived(wire_data)
        handle = self.registry[wire_data.header]
        _logger.debug(f"dispatching request {handle}")
        try:
            await handle(event)
        except Exception:
            if const.debug:
                traceback.print_exc()
            raise


async def send_discovery_requests(transport, multicast_addr):
    this_rp = get_this_remote_peer()
    ping_data = bytes(
        WireData(
            DISCOVERY.NETWORK_FIND,
            this_rp.peer_id,
            reply_addr=this_rp.req_uri[:2]
        )
    )

    async def send_discovery_packet():

        async for _ in use.async_timeouts(initial=0.1, max_retries=const.DISCOVER_RETRIES):
            transport.sendto(ping_data, multicast_addr)
            if Dock.kademlia_network_server.is_bootstrapped:
                Dock.in_network.set()  # set the signal informing that we are in network
                break

        _logger.debug(f"sent discovery request to multicast {multicast_addr}")

    async def enter_passive_mode():
        _logger.info(f"entering passive mode for discovery after waiting for {const.DISCOVER_TIMEOUT}s")
        async for _ in use.async_timeouts(initial=0.1, max_retries=-1, max_value=const.DISCOVER_TIMEOUT):
            if Dock.finalizing.is_set():
                return
            if Dock.kademlia_network_server.is_bootstrapped:
                continue

            Dock.in_network.clear()  # set to false, signalling that we are no longer connect to network
            await send_discovery_packet()

    await send_discovery_packet()

    await asyncio.sleep(const.DISCOVER_TIMEOUT)  # wait a bit
    # stay in passive mode and keep sending discovery requests

    task = asyncio.create_task(enter_passive_mode())

    # try requesting user a host name of peer that is already in network
    if not Dock.kademlia_network_server.is_bootstrapped:
        _logger.debug(f"requesting user for peer name after waiting for {const.DISCOVER_TIMEOUT}s")
        await _try_asking_user(transport, ping_data)

    await task


async def _try_asking_user(transport, discovery_packet):
    if peer_name := await webpage.ask_user_for_a_peer():
        try:
            async for family, sock_type, proto, _, addr in use.get_addr_info(peer_name, const.PORT_REQ):
                transport.sendto(discovery_packet, addr)
        except OSError:
            await webpage.failed_to_reach(peer_name)
