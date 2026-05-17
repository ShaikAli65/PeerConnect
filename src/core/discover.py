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
from typing import NamedTuple

import src.net.utils as net_util
from src import net
from src.avails import Router, WireData, const, use
from src.core.user_prompts import UserPrompts
from src.transfers import DISCOVERY

_logger = logging.getLogger(__name__)


async def discovery_initiate(
        multicast_address,
        requests_dispatcher,
        interface,
        this_remote_peer,
        kad_server,
        in_network,
        finalizing_event,
        transport,
        user_prompts: UserPrompts,
):
    """Initializes discovery dispatcher and transport; registers handlers; sends multicast requests"""
    discovery_router = Router()
    discovery_transport = net.DiscoveryTransport(transport)
    requests_dispatcher.register_handler(net.REQUESTS_HEADERS.DISCOVERY, discovery_router)

    discovery_reply_handler = DiscoveryReplyHandler(interface, kad_server)
    discovery_req_handler = DiscoveryRequestHandler(
        discovery_transport,
        this_remote_peer,
        interface,
    )

    discovery_router.register_handler(DISCOVERY.NETWORK_FIND_REPLY, discovery_reply_handler)
    discovery_router.register_handler(DISCOVERY.NETWORK_FIND, discovery_req_handler)

    # TODO: who is the owner of this task??
    asyncio.create_task(
        send_discovery_requests(
            multicast_address,
            kad_server,
            in_network,
            finalizing_event,
            discovery_transport,
            this_remote_peer,
            user_prompts,
        )
    )
    return DiscoveryService(discovery_transport, discovery_router)


def DiscoveryReplyHandler(interface, kad_server):
    async def handle(event: net.RequestEvent):
        if event.from_addr[0] == interface.ip:
            return
        connect_address = tuple(event.request["connect_uri"])
        _logger.debug(f"from: {event.from_addr}, {connect_address=}")
        if any(await kad_server.bootstrap([connect_address])):
            _logger.debug("bootstrapping completed")

    return handle


def DiscoveryRequestHandler(discovery_transport, this_remote_peer, this_interface):
    async def handle(event: net.RequestEvent):
        req_packet = event.request
        if req_packet["reply_addr"][0] == this_interface.ip[0]:
            _logger.debug(f"ignoring echo, {req_packet['reply_addr']}")
            return
        _logger.info(f"discovery replying to req: {req_packet.body}")
        data_payload = WireData(
            header=DISCOVERY.NETWORK_FIND_REPLY,
            msg_id=this_remote_peer.peer_id,
            connect_uri=this_remote_peer.req_uri[:2],
        )
        discovery_transport.sendto(
            bytes(data_payload), this_interface.addr_tuple(*req_packet["reply_addr"][:2])
        )

    return handle


class DiscoveryService(NamedTuple):
    transport: net.DiscoveryTransport
    router: Router


async def send_discovery_requests(multicast_addr,
                                  kad_server,
                                  in_network,
                                  finalizing,
                                  transport,
                                  this_remote_peer,
                                  user_prompts: UserPrompts):
    """Sends multicast discovery requests with timeouts and passive fallback; queries user for peer name if unbootstrapped"""

    ping_data = bytes(
        WireData(
            DISCOVERY.NETWORK_FIND,
            this_remote_peer.peer_id,
            reply_addr=this_remote_peer.req_uri[:2]
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
        await _try_asking_user(transport, ping_data, user_prompts)

    if not task.done():
        await task


async def _try_asking_user(transport, discovery_packet, user_prompts: UserPrompts):
    reason = None
    while True:
        if peer_name := await user_prompts.ask_discovery_peer_name(reason):
            try:
                async for family, sock_type, proto, _, addr in net_util.get_addr_info(
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
