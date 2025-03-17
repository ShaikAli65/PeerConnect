"""
This is Frontend, Frontend is This
Interfacing with UI using websockets

"""

import asyncio
import asyncio as _asyncio
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import overload

import websockets
from websockets import ConnectionClosedError, WebSocketServerProtocol

from src.avails import DataWeaver, InvalidPacket, const, use
from src.avails.bases import BaseDispatcher
from src.avails.exceptions import TransferIncomplete
from src.avails.mixins import QueueMixIn, ReplyRegistryMixIn, \
    singleton_mixin
from src.conduit import headers, logger
from src.core.app import AppType

PROFILE_WAIT: _asyncio.Future | None = None

# maintain separate exit stack, so that we can maintain nested exits in a better way
# without filling up Dock.exit_stack which has more critical exit ordering
_exit_stack = AsyncExitStack()


class FrontEndWebSocket:
    """Wrapping a Websocket Transport with buffering"""

    def __init__(self, transport=None, buffer_size=const.MAX_FRONTEND_MESSAGE_BUFFER_LEN, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stopping = False
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
            logger.debug(f"[PAGE HANDLE] ! transport not connected buffering data: {data=}")

            await self._add_to_buffer(data)
            return

        try:
            logger.debug(f"[PAGE HANDLE] > data to page: {data=}")
            await self.transport.send(str(data))
        except websockets.WebSocketException as wse:
            self._is_transport_connected = False
            await self._add_to_buffer(data)
            raise TransferIncomplete from wse

    async def _send_buffer(self):
        while self.stopping is False:
            async with self.ping_sender:
                await self.ping_sender.wait()

            while self.stopping is False:
                msg = await self.buffer.get()
                try:
                    logger.debug(f"[PAGE HANDLE] > data to page: {msg=}")
                    await self.transport.send(msg)
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

        if self.transport:
            await self.transport.close()

        if (t := getattr(self, '_buffer_sender_task', None)) and not t.done():
            await use.safe_cancel_task(t)

        logger.debug("closed front end websocket")
        self._finalized = True


@singleton_mixin
class FrontEndDispatcher(QueueMixIn, BaseDispatcher):
    """
    Dispatcher that SENDS packets to frontend >>
    """

    async def add_websocket(self, type_code, ws):
        """Adds websocket to registry with given type code

        """
        self.register_handler(type_code, ws)

    def get_websocket(self, type_code) -> FrontEndWebSocket:
        return self.get_handler(type_code)

    async def submit(self, msg_packet: DataWeaver):
        """> Outgoing (to frontend)"""
        try:
            return await self.registry[msg_packet.type].submit(msg_packet.dump())
        except TransferIncomplete as ti:
            logger.info(f"cannot send msg to frontend {msg_packet}", exc_info=ti)


@singleton_mixin
class MessageFromFrontEndDispatcher(QueueMixIn, ReplyRegistryMixIn, BaseDispatcher):
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def submit(self, data_weaver):
        await self.registry[data_weaver.type](data_weaver)


async def validate_connection(web_socket, *, _exit_stack=_exit_stack):
    try:
        wire_data = await _asyncio.wait_for(web_socket.recv(), const.SERVER_TIMEOUT)
    except TimeoutError as te:
        logger.error(f"[PAGE HANDLE] timeout reached, cancelling {web_socket=}")
        await web_socket.close()
        raise ConnectionError from te
    except ConnectionClosedError as cce:
        raise ConnectionError from cce

    verification = DataWeaver(serial_data=wire_data)
    front_end_disp = FrontEndDispatcher()
    if disp := front_end_disp.get_websocket(verification.type):
        await disp.update_transport(web_socket)
    else:
        web_socket_disp = FrontEndWebSocket(transport=web_socket)
        await _exit_stack.enter_async_context(web_socket_disp)
        await front_end_disp.add_websocket(verification.type, web_socket_disp)

    logger.info("[PAGE HANDLE] waiting for data from websocket")


async def _handle_client(web_socket: WebSocketServerProtocol):
    try:
        await validate_connection(web_socket)
    except ConnectionError:
        return
    front_end_data_disp = MessageFromFrontEndDispatcher()
    is_registered_for_reply = front_end_data_disp.is_registered
    recv = web_socket.recv

    while True:
        data = await recv()

        logger.debug(f"[PAGE HANDLE] < data from page: {data=}")
        parsed_data = DataWeaver(serial_data=data)

        try:
            parsed_data.field_check()
        except InvalidPacket as ip:
            logger.debug("[PAGE HANDLE]", exc_info=ip)
            continue

        if is_registered_for_reply(parsed_data):
            logger.debug(f"a reply is registered for {parsed_data.msg_id}")
            front_end_data_disp.msg_arrived(parsed_data)
            continue

        front_end_data_disp(parsed_data)


async def _handle_client_exp_logging_wrapper(*args, **kwargs):
    try:
        await _handle_client(*args, **kwargs)
    except websockets.WebSocketException as we:
        logger.error(f"error occured in handler exp:{we}")


@asynccontextmanager
async def start_websocket_server():
    try:
        start_server = await websockets.serve(_handle_client_exp_logging_wrapper, const.WEBSOCKET_BIND_IP,
                                              const.PORT_PAGE)
    except OSError:
        print(const.BIND_FAILED)
        logger.critical("failed to bind websocket", exc_info=True)
        sys.exit(-1)

    logger.info(f"[PAGE HANDLE] websocket server started at ws://{const.WEBSOCKET_BIND_IP}:{const.PORT_PAGE}")
    try:
        async with start_server:
            yield
    finally:
        await start_server.wait_closed()
        logger.info("[PAGE HANDLE] websocket server closed")


def _http_server(bind, port, directory):
    class HTTPServer(ThreadingHTTPServer):
        def finish_request(self, request, client_address):
            self.RequestHandlerClass(request, client_address, self, directory=directory)

    with HTTPServer((bind, port), SimpleHTTPRequestHandler) as httpd:
        host, port = httpd.socket.getsockname()[:2]
        url_host = f'[{host}]' if ':' in host else host
        logger.info(
            f"Serving HTTP on {host} port {port} "
            f"(http://{url_host}:{port}/) ..."
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("\nKeyboard interrupt received, exiting.")


def run_page_server(host="localhost", _exit_stack=_exit_stack):
    async def _helper():
        with ProcessPoolExecutor(1) as pool:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(pool, _http_server, host, const.PORT_PAGE_SERVE, const.PATH_PAGE)

    run_server = asyncio.create_task(_helper(), name="http-demon-for-frontend")
    _exit_stack.push_async_callback(use.safe_cancel_task, run_server)


async def initiate_page_handle(app: AppType, *, _exit_stack=_exit_stack):
    global PROFILE_WAIT
    PROFILE_WAIT = _asyncio.get_event_loop().create_future()

    await app.exit_stack.enter_async_context(_exit_stack)

    front_end = FrontEndDispatcher()
    # these transports will get, set later when websocket connection from frontend arrives
    await front_end.add_websocket(headers.DATA, fEwSd := FrontEndWebSocket())
    await _exit_stack.enter_async_context(fEwSd)
    await front_end.add_websocket(headers.SIGNALS, fEwSd := FrontEndWebSocket())
    await _exit_stack.enter_async_context(fEwSd)

    from src.conduit.handlesignals import FrontEndSignalDispatcher
    from src.conduit.handledata import FrontEndDataDispatcher

    signal_disp = FrontEndSignalDispatcher()
    data_disp = FrontEndDataDispatcher()
    signal_disp.register_all()
    data_disp.register_all()

    msg_disp = MessageFromFrontEndDispatcher()

    msg_disp.register_handler(headers.DATA, data_disp.submit)
    msg_disp.register_handler(headers.SIGNALS, signal_disp.submit)

    run_page_server()
    await _exit_stack.enter_async_context(msg_disp)
    await _exit_stack.enter_async_context(front_end)
    await _exit_stack.enter_async_context(start_websocket_server())


@overload
def front_end_data_dispatcher(data, expect_reply=False): ...


@overload
def front_end_data_dispatcher(data, expect_reply=True) -> _asyncio.Future[DataWeaver]: ...


def front_end_data_dispatcher(data, expect_reply=False):
    """Send a packet to frontend based on type code

    Args:
        data(DataWeaver): packet to send
        expect_reply: if expecting a reply, this function returns an asyncio.Future

    Returns:
        Future[DataWeaver] | Task

    Raises:
        InvalidPacket: if msg does not contain msg_id and expecting a reply

    """
    disp = FrontEndDispatcher()
    msg_disp = MessageFromFrontEndDispatcher()

    r = disp(data)

    if expect_reply:
        if data.msg_id is None:
            raise InvalidPacket("msg_id not found and expecting a reply")

        return msg_disp.register_reply(data.msg_id)

    return r
