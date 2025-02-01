import asyncio as _asyncio
import contextlib
import functools
from asyncio import Future
from collections import deque
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, overload

import websockets

from src.avails import DataWeaver, InvalidPacket, const
from src.avails.bases import BaseDispatcher
from src.avails.events import StreamDataEvent
from src.avails.exceptions import TransferIncomplete
from src.avails.mixins import QueueMixIn, ReplyRegistryMixIn, singleton_mixin
from src.core import Dock
from src.transfers import HEADERS
from src.webpage_handlers import headers, logger

PROFILE_WAIT = _asyncio.Event()

if TYPE_CHECKING:
    from websockets.asyncio.connection import Connection
else:
    Connection = None


class FrontEndWebSocketDispatcher(BaseDispatcher):
    def __init__(self, transport, *args, buffer_size=const.MAX_FRONTEND_MESSAGE_BUFFER_LEN, **kwargs):
        super().__init__(transport=transport, stop_flag=None, *args, **kwargs)
        self.max_buffer_size = buffer_size
        self.buffer = deque(maxlen=buffer_size)
        self._is_transport_connected = True

    def update_transport(self, transport):
        self._is_transport_connected = True
        self.transport = transport

    async def submit(self, data: DataWeaver):

        if not self._is_transport_connected:
            self.buffer.append(data)
            return

        try:
            await self.transport.send(str(data))
        except websockets.WebSocketException as wse:
            self._is_transport_connected = False
            self._handle_buffer_and_log()
            self.buffer.append(data)
            raise TransferIncomplete from wse

        await self._send_buffer()

    async def _send_buffer(self):
        while len(self.buffer) > 0:
            msg = self.buffer.popleft()
            try:
                await self.transport.send(str(msg))
            except websockets.WebSocketException as wse:
                self._is_transport_connected = False
                self._handle_buffer_and_log()
                self.buffer.appendleft(msg)
                raise TransferIncomplete from wse

    def _handle_buffer_and_log(self):
        if len(self.buffer) >= self.max_buffer_size:
            logger.warning(f"discarding websocket message {self.buffer.popleft()}, buffer full", exc_info=True)

    async def __aexit__(self, exc_type, exc_val, exc_tb):

        if self._is_transport_connected:
            # try to flush all the buffer
            await self.submit(DataWeaver())

        if len(self.buffer) > 0:
            logger.warning(f"websocket buffer not empty {self.buffer}")

        await self.transport.close()


@singleton_mixin
class FrontEndDispatcher(QueueMixIn, BaseDispatcher):
    """
    Dispatcher that SENDS packets to frontend
    """

    __slots__ = 'stop_flag', 'dispatchers'

    def __init__(self, stop_flag=None):
        super().__init__(transport=None, stop_flag=stop_flag)

        self.stop_flag = stop_flag or Dock.finalizing.is_set
        self.dispatchers = {}
        self.dispatchers_exit_stack = AsyncExitStack()

    def add_dispatcher(self, type_code, *dispatchers):
        for dispatcher in dispatchers:
            self.dispatchers[type_code] = dispatcher
            self.dispatchers_exit_stack.push_async_exit(dispatcher)

    def update_dispatcher(self, type_code, *dispatchers):
        for dispatcher in dispatchers:
            self.dispatchers[type_code] = dispatcher
            self.dispatchers_exit_stack.push_async_exit(dispatcher)

    def get_dispatcher(self, type_code):
        return self.dispatchers.get(type_code, None)

    async def submit(self, msg_packet: DataWeaver):
        """Outgoing"""
        try:
            return await self.dispatchers[msg_packet.type](msg_packet)
        except TransferIncomplete as ti:
            logger.error(f"cannot send msg to frontend {msg_packet}, exp={ti}")

    async def __aenter__(self):
        await self.dispatchers_exit_stack.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.dispatchers_exit_stack.__aexit__(exc_type, exc_val, exc_tb)


class ReplyRegistry(ReplyRegistryMixIn):
    def register_reply(self, data_weaver):
        data_weaver.msg_id = self.id_factory
        return super().register_reply(data_weaver.msg_id)


@singleton_mixin
class MessageFromFrontEndDispatcher(QueueMixIn, BaseDispatcher):
    __slots__ = ()

    def __init__(self, reply_registry, *args, **kwargs):
        super().__init__(transport=None, stop_flag=None, *args, **kwargs)
        self.reply_registry = reply_registry

    async def submit(self, data_weaver):
        if self.reply_registry.is_registered(data_weaver.msg_id):
            return self.reply_registry.msg_arrived(data_weaver)

        await self.registry[data_weaver.type](data_weaver)

    @functools.wraps(ReplyRegistry.register_reply)
    def register_reply(self, msg):
        return self.reply_registry.register_reply(msg)


async def validate_connection(web_socket):
    try:
        wire_data = await _asyncio.wait_for(web_socket.recv(), const.SERVER_TIMEOUT)
    except TimeoutError:
        logger.error(f"[PAGE HANDLE] timeout reached, cancelling {web_socket=}")
        await web_socket.close()
        raise ConnectionError() from None

    verification = DataWeaver(serial_data=wire_data)

    if disp := FrontEndDispatcher().get_dispatcher(verification.type):
        disp.update_transport(web_socket)
    else:
        web_socket_disp = FrontEndWebSocketDispatcher(transport=web_socket)
        FrontEndDispatcher().add_dispatcher(verification.type, web_socket_disp)

    logger.info("[PAGE HANDLE] waiting for data from websocket")


async def handle_client(web_socket: Connection):
    try:
        try:
            await validate_connection(web_socket)
        except ConnectionError:
            return

        async for data in web_socket:
            logger.info(f"[PAGE HANDLE] data from page: {data=}")
            parsed_data = DataWeaver(serial_data=data)

            try:
                parsed_data.field_check()
            except InvalidPacket as ip:
                logger.debug("[PAGE HANDLE]", exc_info=ip)
                continue

            MessageFromFrontEndDispatcher()(parsed_data)

    except websockets.exceptions.ConnectionClosed:
        logger.info("[PAGE HANDLE] Websocket Connection closed")


@contextlib.asynccontextmanager
async def start_websocket_server():
    start_server = await websockets.serve(handle_client, const.WEBSOCKET_BIND_IP, const.PORT_PAGE)
    logger.info(f"[PAGE HANDLE] websocket server started at ws://{const.WEBSOCKET_BIND_IP}:{const.PORT_PAGE}")

    try:
        async with start_server:
            yield
    except Exception:
        logger.info("[PAGE HANDLE] ending websocket server")
        raise


async def initiate_page_handle():
    front_end = FrontEndDispatcher(transport=None, stop_flag=Dock.finalizing.is_set)
    front_end.add_dispatcher(headers.DATA, FrontEndWebSocketDispatcher(None))
    front_end.add_dispatcher(headers.SIGNALS, FrontEndWebSocketDispatcher(None))

    from src.webpage_handlers.handlesignals import FrontEndSignalDispatcher
    from src.webpage_handlers.handledata import FrontEndDataDispatcher
    signal_disp = FrontEndSignalDispatcher(transport=None, stop_flag=Dock.finalizing.is_set)
    data_disp = FrontEndDataDispatcher(transport=None, stop_flag=Dock.finalizing.is_set)

    msg_disp = MessageFromFrontEndDispatcher(ReplyRegistry())
    msg_disp.register_handler(headers.DATA, data_disp.submit)
    msg_disp.register_handler(headers.SIGNALS, signal_disp.submit)

    async with AsyncExitStack() as exit_s:
        await exit_s.enter_async_context(front_end)
        await exit_s.enter_async_context(msg_disp)
        await exit_s.enter_async_context(start_websocket_server())
        await Dock.finalizing.wait()


@overload
def front_end_data_dispatcher(data, expect_reply=False): ...


@overload
def front_end_data_dispatcher(data, expect_reply=True) -> _asyncio.Future[DataWeaver]: ...


def MessageHandler():
    async def handler(event: StreamDataEvent):
        front_end_data_dispatcher(DataWeaver(
            header=event.data.header,
            content=event.data["message"],
            peer_id=event.data.peer_id,
        ))

    return handler


def register_handler_to_acceptor(acceptor_disp):
    return acceptor_disp.register_handler(
        HEADERS.CMD_TEXT,
        MessageHandler()
    )


def front_end_data_dispatcher(data, expect_reply=False) -> Future[DataWeaver | None]:
    disp = FrontEndDispatcher()
    msg_disp = MessageFromFrontEndDispatcher()
    if expect_reply:
        return msg_disp.register_reply(data)
    return disp(data)
