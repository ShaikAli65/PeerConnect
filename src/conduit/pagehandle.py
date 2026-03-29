"""
This is Frontend, Frontend is This
Interfacing with UI using websockets

"""

import asyncio
import asyncio as _asyncio
import logging
import sys
from asyncio import TaskGroup
from concurrent.futures import ProcessPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import websockets
from websockets import ConnectionClosedError, WebSocketServerProtocol

from src.avails import const, use
from src.avails.exceptions import InvalidPacket, TransferIncomplete
from src.avails.mixins import BasicDispatcher, Dispatcher, singleton_mixin
from src.conduit import headers
from src.conduit.app_event_subs import sub_to_remote_peer_updates
from src.conduit.ui_codec import DataWeaver
from src.configurations.appconfig import AppConfig, AppRunTime
from src.core.app_events import AppEventsBus

logger = logging.getLogger(__name__)

PROFILE_WAIT: _asyncio.Future | None = None

# maintain separate exit stack, so that we can maintain nested exits in a better way
# without filling up App.exit_stack which has more critical exit ordering
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
            logger.debug(f"! transport not connected buffering data: {data=}")

            await self._add_to_buffer(data)
            return

        try:
            logger.debug(f"> data to page: {data=!r}")
            await self.transport.send(str(data))
        except websockets.WebSocketException as wse:
            self._is_transport_connected = False
            await self._add_to_buffer(data)
            raise TransferIncomplete from wse

    async def _send_buffer(self):
        while not self.stopping:
            async with self.ping_sender:
                await self.ping_sender.wait()

            while not self.stopping:
                msg = await self.buffer.get()
                try:
                    logger.debug(f"> data to page: {msg=!r}")
                    await self.transport.send(str(msg))
                except websockets.WebSocketException:
                    await self._add_to_buffer(msg)
                    self._is_transport_connected = False
                    break
                except AttributeError:
                    # transport is None, and we got \\"None does not have .send"\\ thing
                    break

    async def _add_to_buffer(self, msg: DataWeaver):
        self._handle_buffer_and_log()
        return await self.buffer.put(msg)

    def _handle_buffer_and_log(self):
        """Logs a warning and removes top element from queue"""
        if self.buffer.qsize() >= self.max_buffer_size:
            return logger.warning(f"discarding websocket message {self.buffer.get_nowait()}, buffer full",
                                  exc_info=True)
        return None

    async def __aenter__(self):
        self._buffer_sender_task = _asyncio.create_task(self._send_buffer(),
                                                        name="frontend-websocket-watcher")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._finalized:
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
class FrontEndConnector(*BasicDispatcher):
    """Connections to frontend
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
            return logger.info(f"! cannot send msg to frontend {msg_packet}", exc_info=ti)


@singleton_mixin
class MessageFromFrontEndDispatcher(*Dispatcher):
    __slots__ = ()

    async def submit(self, data_weaver):
        return await self.call_handler(
            data_weaver.header,
            logger,
            data_weaver
        )

    async def __aexit__(self, *args):
        async def bomb():
            raise InterruptedError

        self._task_group.create_task(bomb())

        try:
            return await super().__aexit__(*args)
        except* InterruptedError:
            logger.debug("suppressing expected interrupted error at aexit")

        return None


async def validate_connection(web_socket, *, _exit_stack=_exit_stack):
    try:
        wire_data = await _asyncio.wait_for(web_socket.recv(), const.SERVER_TIMEOUT)
    except TimeoutError as te:
        logger.error(f"timeout reached, cancelling {web_socket=}")
        await web_socket.close()
        raise ConnectionError from te
    except ConnectionClosedError as cce:
        raise ConnectionError from cce

    verification = DataWeaver(serial_data=wire_data)
    front_end_disp = FrontEndConnector()
    if disp := front_end_disp.get_websocket(verification.type):
        await disp.update_transport(web_socket)
    else:
        web_socket_disp = FrontEndWebSocket(transport=web_socket)
        await _exit_stack.enter_async_context(web_socket_disp)
        await front_end_disp.add_websocket(verification.type, web_socket_disp)

    logger.info("waiting for data from websocket")


async def _handle_ui(web_socket: WebSocketServerProtocol):
    try:
        await validate_connection(web_socket)
    except ConnectionError:
        return
    front_end_data_disp = MessageFromFrontEndDispatcher()
    recv = web_socket.recv

    while True:
        data = await recv()

        parsed_data = DataWeaver(serial_data=data)
        logger.debug(f"< data from page: {parsed_data=!r}")

        try:
            parsed_data.field_check()
        except InvalidPacket as ip:
            logger.debug("[PAGE HANDLE]", exc_info=ip)
            continue

        if front_end_data_disp.is_registered(parsed_data):
            logger.debug(f"a reply is registered for {parsed_data.msg_id}")
            front_end_data_disp.reply_arrived(parsed_data)
            continue

        front_end_data_disp(parsed_data)


async def _handle_ui_exp_logging_wrapper(*args, **kwargs):
    try:
        await _handle_ui(*args, **kwargs)
    except websockets.WebSocketException as we:
        logger.error(f"error occurred in handler exp:{we}")


@asynccontextmanager
async def start_websocket_server():
    try:
        start_server = await websockets.serve(_handle_ui_exp_logging_wrapper, const.WEBSOCKET_BIND_IP,
                                              const.PORT_PAGE)
    except OSError as oe:
        print(const.BIND_FAILED_MSG)
        logger.critical(f"failed to bind websocket: {oe}")
        sys.exit(-1)

    logger.info(f"websocket server started at ws://{const.WEBSOCKET_BIND_IP}:{const.PORT_PAGE}")
    try:
        async with start_server:
            yield
    finally:
        await start_server.wait_closed()
        logger.info("websocket server closed")


def _http_server(bind, port, directory):
    class HTTPServer(ThreadingHTTPServer):
        def finish_request(self, request, client_address):
            self.RequestHandlerClass(request, client_address, self, directory=directory)  # noqa

    with HTTPServer((bind, port), SimpleHTTPRequestHandler) as httpd:  # noqa
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


def run_page_server(host="localhost", port_page_serve=const.PORT_PAGE_SERVE, _exit_stack=_exit_stack):
    async def _helper():
        with ProcessPoolExecutor(1) as pool:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(pool, _http_server, host, port_page_serve, const.PATH_PAGE)

    run_server = asyncio.create_task(_helper(), name="http-demon-for-frontend")
    _exit_stack.push_async_callback(use.safe_cancel_task, run_server)


def subscribe_to_app_events(app_events: AppEventsBus, task_group: asyncio.TaskGroup):
    sub_to_remote_peer_updates(app_events, task_group)


async def initiate_page_handle(
        app_config: AppConfig,
        app_runtime: AppRunTime,
        *,
        _exit_stack=_exit_stack,
):
    await app_runtime.exit_stack.enter_async_context(_exit_stack)

    global PROFILE_WAIT
    if PROFILE_WAIT is None:
        PROFILE_WAIT = _asyncio.get_event_loop().create_future()

    # responsible for sending messages to frontend, composed with multiple FrontEndWebSockets
    front_end = FrontEndConnector()

    # these transports will get, set later when websocket connection from frontend arrives
    await front_end.add_websocket(headers.DATA, fEwSd := FrontEndWebSocket())
    await _exit_stack.enter_async_context(fEwSd)

    await front_end.add_websocket(headers.SIGNALS, fEwSd := FrontEndWebSocket())
    await _exit_stack.enter_async_context(fEwSd)

    from src.conduit import handlesignals, handledata

    msg_disp = MessageFromFrontEndDispatcher()
    # messages from front end fed into this dispatcher, and it dispatches
    # them to respectively modules' dispatchers
    handlesignals.register_handlers(msg_disp)
    handledata.register_handlers(msg_disp)

    run_page_server(port_page_serve=app_config.page_serve_port)

    tg = TaskGroup()
    await _exit_stack.enter_async_context(tg)
    subscribe_to_app_events(app_runtime.app_events, tg)

    await _exit_stack.enter_async_context(msg_disp)
    await _exit_stack.enter_async_context(front_end)
    await _exit_stack.enter_async_context(start_websocket_server())
    return PROFILE_WAIT
