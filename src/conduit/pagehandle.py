import asyncio as _asyncio
import functools
from asyncio import Future
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, overload

import websockets

from src.avails import DataWeaver, InvalidPacket, const
from src.avails.bases import BaseDispatcher
from src.avails.events import MessageEvent
from src.avails.exceptions import TransferIncomplete
from src.avails.mixins import AExitStackMixIn, QueueMixIn, ReplyRegistryMixIn, singleton_mixin
from src.conduit import headers, logger
from src.core.public import Dock
from src.transfers import HEADERS

PROFILE_WAIT = _asyncio.Event()

if TYPE_CHECKING:
    from websockets.asyncio.connection import Connection
else:
    Connection = None

# maintain separate exit stack, so that we can maintain nested exits in a better way
# without filling up Dock.exit_stack which has more critical exit ordering
_exit_stack = AsyncExitStack()


class FrontEndWebSocketDispatcher(BaseDispatcher):
    def __init__(self, transport=None, buffer_size=const.MAX_FRONTEND_MESSAGE_BUFFER_LEN, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stopping_event = _asyncio.Event()
        self.ping_sender = _asyncio.Condition()
        self.max_buffer_size = buffer_size
        self.buffer = _asyncio.Queue(buffer_size)
        if transport:
            self._is_transport_connected = True
        else:
            self._is_transport_connected = False
        self.transport = transport
        self._finalized = False

    async def update_transport(self, transport):
        self._is_transport_connected = True
        self.transport = transport
        async with self.ping_sender:
            self.ping_sender.notify_all()

    async def submit(self, data: DataWeaver):

        if not self._is_transport_connected:
            await self._add_to_buffer(data)
            return

        try:
            await self.transport.send(str(data))
        except websockets.WebSocketException as wse:
            self._is_transport_connected = False
            await self._add_to_buffer(data)
            raise TransferIncomplete from wse

    async def _send_buffer(self):
        stop_flag = self.stopping_event.is_set
        while True:
            async with self.ping_sender:
                await self.ping_sender.wait()
            if stop_flag():
                break
            while True:
                msg = await self.buffer.get()
                if stop_flag():
                    break
                try:
                    await self.transport.send(str(msg))
                except websockets.WebSocketException:
                    await self._add_to_buffer(msg)
                    self._is_transport_connected = False
                    break
                except AttributeError:
                    # transport is None, and we got \\"None does not have .send"\\ thing
                    break

    async def _add_to_buffer(self, msg):
        self._handle_buffer_and_log()
        return await self.buffer.put(msg)

    def _handle_buffer_and_log(self):
        if self.buffer.qsize() >= self.max_buffer_size:
            return logger.warning(f"discarding websocket message {self.buffer.get_nowait()}, buffer full",
                                  exc_info=True)

    async def __aenter__(self):
        self._buffer_sender_task = _asyncio.create_task(self._send_buffer())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._finalized is True:
            return

        if not self.buffer.empty():
            logger.warning(f"websocket buffer not empty len={self.buffer.qsize()}")

        self.stopping_event.set()

        async with self.ping_sender:
            self.ping_sender.notify_all()

        await self.buffer.put(None)  # wake up if it's waiting for any message
        if self.transport:
            await self.transport.close()

        await self._buffer_sender_task
        self._finalized = True


@singleton_mixin
class FrontEndDispatcher(QueueMixIn, AExitStackMixIn, BaseDispatcher):
    """
    Dispatcher that SENDS packets to frontend
    """

    async def add_dispatcher(self, type_code, dispatcher):
        """Adds dispatcher to watch list

        Enters context of dispatchers passed in,
        owns lifetime of those dispatchers

        Args:
            type_code(int):
            dispatcher:

        """
        self.register_handler(type_code, dispatcher)
        await self._exit_stack.enter_async_context(dispatcher)

    def get_dispatcher(self, type_code) -> FrontEndWebSocketDispatcher:
        return self.get_handler(type_code)

    async def submit(self, msg_packet: DataWeaver):
        """Outgoing (to frontend)"""
        try:
            return await self.registry[msg_packet.type](msg_packet)
        except TransferIncomplete as ti:
            logger.error(f"cannot send msg to frontend {msg_packet}, exp={ti}")


class ReplyRegistry(ReplyRegistryMixIn):
    def register_reply(self, data_weaver):
        data_weaver.msg_id = self.id_factory
        return super().register_reply(data_weaver.msg_id)


@singleton_mixin
class MessageFromFrontEndDispatcher(QueueMixIn, BaseDispatcher):
    __slots__ = ()

    def __init__(self, reply_registry, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        await disp.update_transport(web_socket)
    else:
        web_socket_disp = FrontEndWebSocketDispatcher(transport=web_socket)
        await (fd := FrontEndDispatcher()).add_dispatcher(verification.type, web_socket_disp)
        await _exit_stack.enter_async_context(fd)

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


@asynccontextmanager
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
    front_end = FrontEndDispatcher()

    # these transports will get, set later when websocket connection from frontend arrives
    await front_end.add_dispatcher(headers.DATA, FrontEndWebSocketDispatcher())

    await front_end.add_dispatcher(headers.SIGNALS, FrontEndWebSocketDispatcher())

    from src.conduit.handlesignals import FrontEndSignalDispatcher
    from src.conduit.handledata import FrontEndDataDispatcher

    signal_disp = FrontEndSignalDispatcher()
    data_disp = FrontEndDataDispatcher()
    signal_disp.register_all()
    data_disp.register_all()

    msg_disp = MessageFromFrontEndDispatcher(ReplyRegistry())

    msg_disp.register_handler(headers.DATA, data_disp.submit)
    msg_disp.register_handler(headers.SIGNALS, signal_disp.submit)

    await Dock.exit_stack.enter_async_context(_exit_stack)
    # enter early, cause these contexts are mostly last one to exit

    await _exit_stack.enter_async_context(front_end)
    await _exit_stack.enter_async_context(msg_disp)
    await _exit_stack.enter_async_context(start_websocket_server())


@overload
def front_end_data_dispatcher(data, expect_reply=False): ...


@overload
def front_end_data_dispatcher(data, expect_reply=True) -> _asyncio.Future[DataWeaver]: ...


def front_end_data_dispatcher(data, expect_reply=False) -> Future[DataWeaver | None]:
    disp = FrontEndDispatcher()
    msg_disp = MessageFromFrontEndDispatcher()
    if expect_reply:
        return msg_disp.register_reply(data)
    return disp(data)


def MessageHandler():
    async def handler(event: MessageEvent):
        front_end_data_dispatcher(DataWeaver(
            header=event.msg.header,
            content=event.msg["message"],
            peer_id=event.msg.peer_id,
        ))

    return handler


def register_handler_to_acceptor(acceptor_disp):
    return acceptor_disp.register_handler(
        HEADERS.CMD_TEXT,
        MessageHandler()
    )
