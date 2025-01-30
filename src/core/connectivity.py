import asyncio
import enum
import logging
import time

from src.avails import WireData, connect, const, use
from src.avails.mixins import QueueMixIn
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
        self.peer = peer
        self.serious = serious
        self.status = ConnectivityCheckState.INITIATED


class Connectivity(QueueMixIn):
    _instance = None
    _initialized = False
    __slots__ = 'last_checked', 'stop_flag'

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, stop_flag=None, *args, **kwargs):
        if self.__class__._initialized is True:
            return
        self.last_checked = {}
        self.__class__._initialized = True
        self.stop_flag = stop_flag or Dock.finalizing.is_set
        super().__init__(*args, **kwargs)

    async def submit(self, request: CheckRequest):

        if request.peer in self.last_checked:
            prev_request, fut = self.last_checked[request.peer]
            if request.time_stamp - prev_request.time_stamp <= const.PING_TIME_CHECK_WINDOW:
                return await fut

        self.last_checked[request.peer] = request, (fut := asyncio.ensure_future(self._new_check(request)))
        return await fut

    @staticmethod
    async def _new_check(request):

        ping_data = WireData(
            header=HEADERS.REMOVAL_PING,
            msg_id=use.get_unique_id(str)
        )

        req_dispatcher = Dock.dispatchers[DISPATCHS.REQUESTS]

        fut = req_dispatcher.register_reply(ping_data.msg_id)  # noqa

        _logger.info(f"connectivity check initiating for {request}")
        request.status = ConnectivityCheckState.REQ_CHECK
        succeeded = True

        try:
            await asyncio.wait_for(fut, const.PING_TIMEOUT)
        except TimeoutError:
            # try a tcp connection if network is terrible with UDP

            # or another possibility that is observed:
            # windows does not forward UDP packets to application level when system is locked or sleeping
            # (interfaces shutdown)
            # what's that with QUIC then, and vpn s too

            try:
                request.status = ConnectivityCheckState.CON_CHECK
                with await connect.connect_to_peer(request.peer, timeout=const.PING_TIMEOUT):
                    pass
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


def new_check(peer):
    connector = Connectivity()
    req = CheckRequest(peer, False)
    return req, connector(req)


async def initiate():
    await Dock.exit_stack.enter_async_context(Connectivity())
