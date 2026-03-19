import asyncio
import enum
import logging
import struct
import time

from core.requests import RequestsService
from src.avails import RemotePeer, WireData, const, use
from src.avails.mixins import TaskGroupMixIn
from src.net.events import RequestEvent
from src.transfers import HEADERS
from .connect import connect_to_peer
from .requests import send_request

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


class Connectivity(TaskGroupMixIn):
    __slots__ = 'last_checked',

    def __init__(self, req_service, *args, **kwargs):
        self.last_checked = {}
        self.req_service = req_service
        super().__init__(*args, **kwargs)

    async def submit(self, request: CheckRequest):
        self.last_checked[request.peer] = request, (fut := asyncio.ensure_future(self._new_check(request)))
        return await fut

    async def _new_check(self, request):

        ping_data = WireData(
            header=HEADERS.REMOVAL_PING,
            msg_id=use.get_unique_id(str)
        )

        _logger.debug(f"connectivity check initiating for {request}")

        try:
            t = send_request(self.req_service, ping_data, request.peer, expect_reply=True)
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

    def new_check(self, peer) -> tuple[CheckRequest, asyncio.Future[bool]]:
        """
        Creates a new check request for a given peer and either returns an existing future
        or initiates a new check process.

        This method is responsible for handling check requests by first determining if there
        is an existing recent check for the peer. If a recent check exists, it immediately
        returns the request and its associated future. Otherwise, it creates a new check task.

        Args:
            peer: The peer entity for which the check request is being created.

        Returns:
            A tuple where the first element is an instance of CheckRequest for the given
            peer. The second element is an asyncio.Future object representing the result
            of the check process.
        """

        req = CheckRequest(peer, False)
        if fut := self.check_for_recent(req):
            # return fast without spawning a task within queue mix in
            return req, fut

        return req, self(req)

    def check_for_recent(self, request):
        if request.peer in self.last_checked:
            prev_request, fut = self.last_checked[request.peer]
            if request.time_stamp - prev_request.time_stamp <= const.PING_TIME_CHECK_WINDOW:
                return fut
        return None

    async def __aenter__(self):
        await super().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for _, fut in self.last_checked.values():
            if not fut.done():
                fut.cancel()

        return await super().__aexit__(exc_type, exc_val, exc_tb)


def EchoHandler(this_peer_id, req_transport):
    def handler(req_event: RequestEvent):
        req = req_event.request
        data = WireData(req.header, req.msg_id, this_peer_id)
        return req_transport.sendto(bytes(data), req_event.from_addr)

    return handler


async def initiate(exit_stack, req_service: RequestsService, this_peer_id):
    req_service.dispatcher.register_simple_handler(
        HEADERS.REMOVAL_PING,
        EchoHandler(this_peer_id, req_service.transport)
    )
    connectivity_checker = Connectivity(req_service)
    await exit_stack.enter_async_context(connectivity_checker)
    return connectivity_checker
