import asyncio
import enum
import logging
import struct
import time

from src.avails import RemotePeer, WireData, connect, const, use
from src.avails.events import RequestEvent
from src.avails.mixins import QueueMixIn, singleton_mixin
from src.core.public import get_this_remote_peer, requests_dispatcher, send_msg_to_requests_endpoint
from src.transfers import HEADERS
from src.transfers.transports import RequestsTransport

_logger = logging.getLogger(__name__)


class ConnectivityCheckState(enum.IntEnum):
    INITIATED = enum.auto()
    REQ_CHECK = enum.auto()
    CON_CHECK = enum.auto()
    COMPLETED = enum.auto()


class CheckRequest:
    __slots__ = 'time_stamp', 'peer', 'serious', 'status'

    def __init__(self, peer, serious):
        self.time_stamp = time.monotonic()
        self.peer: RemotePeer = peer
        self.serious = serious
        self.status = ConnectivityCheckState.INITIATED


@singleton_mixin
class Connectivity(QueueMixIn):
    __slots__ = 'last_checked',

    def __init__(self, *args, **kwargs):
        self.last_checked = {}
        super().__init__(*args, **kwargs)

    async def submit(self, request: CheckRequest):
        self.last_checked[request.peer] = request, (fut := asyncio.ensure_future(self._new_check(request)))
        return await fut

    def check_for_recent(self, request):
        if request.peer in self.last_checked:
            prev_request, fut = self.last_checked[request.peer]
            if request.time_stamp - prev_request.time_stamp <= const.PING_TIME_CHECK_WINDOW:
                return fut

    @staticmethod
    async def _new_check(request):

        ping_data = WireData(
            header=HEADERS.REMOVAL_PING,
            msg_id=use.get_unique_id(str)
        )

        _logger.debug(f"connectivity check initiating for {request}")

        try:
            t = send_msg_to_requests_endpoint(ping_data, request.peer, expect_reply=True)
            await asyncio.wait_for(t, const.PING_TIMEOUT)
            return True
        except TimeoutError:
            # try a tcp connection if network is terrible with UDP

            # or another possibility that is observed:
            # windows does not forward packets to application level when system is locked or sleeping
            # (interfaces shutdown)
            pass

        try:
            request.status = ConnectivityCheckState.CON_CHECK
            with await connect.connect_to_peer(request.peer, timeout=const.PING_TIMEOUT) as sock:
                await sock.asendall(struct.pack("!I", 0))
        except OSError:
            request.status = ConnectivityCheckState.COMPLETED
            # okay this one is cooked
            return False
        else:
            return True

    async def __aenter__(self):
        await super().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):

        for _, fut in self.last_checked.values():
            if not fut.done():
                fut.cancel()

        await super().__aexit__(exc_type, exc_val, exc_tb)


def new_check(peer) -> tuple[CheckRequest, asyncio.Future[bool]]:
    connector = Connectivity()
    req = CheckRequest(peer, False)
    if fut := connector.check_for_recent(req):
        # return fast without spawning a task (within queue mix in)
        return req, fut

    return req, connector(req)


def EchoHandler(req_transport: RequestsTransport):
    def handler(req_event: RequestEvent):
        req = req_event.request
        data = WireData(req.header, req.msg_id, get_this_remote_peer().peer_id)
        return req_transport.sendto(bytes(data), req_event.from_addr)

    return handler


async def initiate(app_ctx):
    await app_ctx.exit_stack.enter_async_context(Connectivity())
    req_disp = requests_dispatcher()
    req_disp.register_simple_handler(HEADERS.REMOVAL_PING, EchoHandler(app_ctx.requests_transport))
