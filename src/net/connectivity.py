import asyncio
import enum
import logging
import struct
import time

from src.avails import RemotePeer, WireData, const, use
from src.avails.exceptions import InvalidPacket
from src.avails.mixins import TaskGroupMixIn, singleton_mixin
from src.core.app import AppType, provide_app_ctx
from src.net.events import RequestEvent
from src.transfers import HEADERS
from .connect import connect_to_peer

_logger = logging.getLogger(__name__)


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
class Connectivity(TaskGroupMixIn):
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
            t = send_request(ping_data, request.peer, expect_reply=True)
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
            with await connect_to_peer(request.peer, timeout=const.PING_TIMEOUT) as sock:
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

        return await super().__aexit__(exc_type, exc_val, exc_tb)


def new_check(peer) -> tuple[CheckRequest, asyncio.Future[bool]]:
    connector = Connectivity()
    req = CheckRequest(peer, False)
    if fut := connector.check_for_recent(req):
        # return fast without spawning a task within queue mix in
        return req, fut

    return req, connector(req)


def EchoHandler(app_ctx):
    def handler(req_event: RequestEvent):
        req = req_event.request
        data = WireData(req.header, req.msg_id, app_ctx.this_peer_id)
        return app_ctx.requests.transport.sendto(bytes(data), req_event.from_addr)

    return handler


async def initiate(app_ctx: AppType):
    await app_ctx.exit_stack.enter_async_context(Connectivity())
    app_ctx.requests.dispatcher.register_simple_handler(HEADERS.REMOVAL_PING, EchoHandler(app_ctx.read_only()))
