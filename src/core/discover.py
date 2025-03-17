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
from typing import TYPE_CHECKING

from src.avails import WireData, const, use
from src.avails.bases import BaseDispatcher
from src.avails.events import RequestEvent
from src.avails.mixins import QueueMixIn, ReplyRegistryMixIn
from src.conduit import webpage
from src.core.app import AppType, ReadOnlyAppType
from src.transfers import DISCOVERY, REQUESTS_HEADERS
from src.transfers.transports import DiscoveryTransport

_logger = logging.getLogger(__name__)


async def discovery_initiate(
        multicast_address,
        app_ctx: AppType,
        transport,
):
    discover_dispatcher = DiscoveryDispatcher()
    discovery_transport = DiscoveryTransport(transport)
    await app_ctx.exit_stack.enter_async_context(discover_dispatcher)
    app_ctx.requests.dispatcher.register_handler(REQUESTS_HEADERS.DISCOVERY, discover_dispatcher)

    app_ctx.discovery.dispatcher = discover_dispatcher
    app_ctx.discovery.transport = discovery_transport

    discovery_reply_handler = DiscoveryReplyHandler(app_ctx.read_only())
    discovery_req_handler = DiscoveryRequestHandler(app_ctx.read_only())

    discover_dispatcher.register_handler(DISCOVERY.NETWORK_FIND_REPLY, discovery_reply_handler)
    discover_dispatcher.register_handler(DISCOVERY.NETWORK_FIND, discovery_req_handler)

    await send_discovery_requests(
        multicast_address,
        app_ctx,
    )


def DiscoveryReplyHandler(app_ctx: ReadOnlyAppType):
    async def handle(event: RequestEvent):
        if event.from_addr[0] == app_ctx.this_ip.ip:
            return
        connect_address = tuple(event.request["connect_uri"])
        _logger.debug(f"from: {event.from_addr}, {connect_address=}")
        if any(await app_ctx.kad_server.bootstrap([connect_address])):
            _logger.debug("bootstrapping completed")

    return handle


def DiscoveryRequestHandler(app_ctx: ReadOnlyAppType):
    async def handle(event: RequestEvent):
        req_packet = event.request
        if req_packet["reply_addr"][0] == app_ctx.this_ip.ip[0]:
            _logger.debug(f"ignoring echo, {req_packet['reply_addr']}")
            return
        _logger.info(f"discovery replying to req: {req_packet.body}")
        data_payload = WireData(
            header=DISCOVERY.NETWORK_FIND_REPLY,
            msg_id=app_ctx.this_peer_id,
            connect_uri=app_ctx.this_remote_peer.req_uri[:2],
        )
        app_ctx.discovery.transport.sendto(
            bytes(data_payload), app_ctx.addr_tuple(*req_packet["reply_addr"][:2])
        )

    return handle


class DiscoveryDispatcher(QueueMixIn, ReplyRegistryMixIn, BaseDispatcher):
    __slots__ = ()
    if TYPE_CHECKING:
        transport: DiscoveryTransport

    async def submit(self, event: RequestEvent):
        wire_data = event.request
        self.msg_arrived(wire_data)
        handle = self.registry.get(wire_data.header, None)
        if handle is None:
            return

        _logger.debug(f"dispatching request {handle}")
        try:
            await handle(event)
        except RuntimeError:
            await self._handle_runtime_error(_logger)
        except Exception as exp:
            _logger.error(f"{handle} failed with :", exc_info=exp)


async def send_discovery_requests(multicast_addr, app_ctx):
    kad_server = app_ctx.kad_server
    in_network = app_ctx.in_network
    finalizing = app_ctx.finalizing
    transport = app_ctx.discovery.transport

    ping_data = bytes(
        WireData(
            DISCOVERY.NETWORK_FIND,
            app_ctx.this_peer_id,
            reply_addr=app_ctx.this_remote_peer.req_uri[:2]
        )
    )

    async def send_discovery_packet():

        async for _ in use.async_timeouts(initial=0.1, max_retries=const.DISCOVER_RETRIES):
            if kad_server.is_bootstrapped:
                in_network.set()  # set the signal informing that we are in network
                break
            transport.sendto(ping_data, multicast_addr)

        _logger.debug(f"sent discovery request to multicast {multicast_addr}")

    async def enter_passive_mode():
        _logger.info(f"entering passive mode for discovery after waiting for {const.DISCOVER_TIMEOUT}s")
        async for _ in use.async_timeouts(initial=0.1, max_retries=-1, max_value=const.DISCOVER_TIMEOUT):
            if finalizing.is_set():
                return
            if kad_server.is_bootstrapped:
                in_network.set()  # set the signal informing that we are in network
                continue

            in_network.clear()  # set to false, signalling that we are no longer connect to network
            await send_discovery_packet()

    await send_discovery_packet()

    task = asyncio.create_task(enter_passive_mode(), name="discovery-passive-mode")

    await asyncio.sleep(const.DISCOVER_TIMEOUT)  # wait a bit
    # stay in passive mode and keep sending discovery requests

    # try requesting user a host name of peer that is already in network
    if not kad_server.is_bootstrapped:
        _logger.debug(f"requesting user for peer name after waiting for {const.DISCOVER_TIMEOUT}s")
        await _try_asking_user(transport, ping_data)

    if not task.done():
        await task


async def _try_asking_user(transport, discovery_packet):
    reason = None
    while True:
        if peer_name := await webpage.ask_user_peer_name_for_discovery(reason):
            try:
                async for family, sock_type, proto, _, addr in use.get_addr_info(
                        peer_name,
                        const.PORT_REQ,
                        family=const.IP_VERSION
                ):
                    transport.sendto(discovery_packet, addr)
                    return
            except OSError:
                reason = "failed to reach peer or name look up failed"
        else:
            break  # if the use is not interested in providing a username
