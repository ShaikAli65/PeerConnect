import asyncio
import enum
import logging
import struct
import time

from src.avails import RemotePeer, WireData, connect, const, use
from src.avails.mixins import QueueMixIn, singleton_mixin
from src.core import DISPATCHS, Dock
from src.transfers import HEADERS

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
    __slots__ = 'last_checked', 'stop_flag'

    def __init__(self, stop_flag=None, *args, **kwargs):
        self.last_checked = {}
        self.stop_flag = stop_flag or Dock.finalizing.is_set
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

        req_dispatcher = Dock.dispatchers[DISPATCHS.REQUESTS]

        fut = req_dispatcher.register_reply(ping_data.msg_id)

        _logger.info(f"connectivity check initiating for {request}")
        request.status = ConnectivityCheckState.REQ_CHECK
        succeeded = True
        req_dispatcher.transport.sendto(bytes(ping_data), request.peer.req_uri)

        try:
            await asyncio.wait_for(fut, const.PING_TIMEOUT)
        except TimeoutError:
            # try a tcp connection if network is terrible with UDP

            # or another possibility that is observed:
            # windows does not forward packets to application level when system is locked or sleeping
            # (interfaces shutdown)

            try:
                request.status = ConnectivityCheckState.CON_CHECK
                with await connect.connect_to_peer(request.peer, timeout=const.PING_TIMEOUT) as sock:
                    await sock.asendall(struct.pack("!I", 0))
            except OSError:
                # okay this one is cooked
                succeeded = False

        request.status = ConnectivityCheckState.COMPLETED
        return succeeded

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
        # return fast without spawning a task
        return req, fut

    return req, connector(req)


async def initiate():
    await Dock.exit_stack.enter_async_context(Connectivity())
