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
from contextlib import asynccontextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import websockets
from avails import Router
from avails.mixins import AExitStackMixIn
from conduit.bases import FrontEnd
from conduit.frontend_web import WebFrontend
from conduit.handleprofiles import align_profiles, set_selected_profile
from src.avails import const, use
from src.avails.exceptions import InvalidPacket, TransferIncomplete
from src.avails.mixins import Dispatcher
from src.conduit.app_event_subs import sub_to_remote_peer_updates
from src.conduit.ui_codec import DataWeaver
from src.configurations.appconfig import AppConfig, AppRunTime
from websockets import ConnectionClosedError, WebSocketServerProtocol

logger = logging.getLogger(__name__)

PROFILE_WAIT: _asyncio.Future | None = None


class FrontEndWebSocket:
    """Wrapping a Websocket Transport with buffering

    Notes:
        * Does not own the websocket transport, context manager enter and exit should be dealt with by the caller

    """

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

    async def __call__(self, data: DataWeaver):

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
        self._may_be_prune_buffer()
        return await self.buffer.put(msg)

    def _may_be_prune_buffer(self):
        """Logs a warning and removes top element from queue"""
        if self.buffer.qsize() >= self.max_buffer_size:
            logger.warning(
                f"discarding websocket message {self.buffer.get_nowait()}, buffer full",
                exc_info=True,
            )
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

        if (t := getattr(self, '_buffer_sender_task', None)) and not t.done():
            await use.safe_cancel_task(t)

        logger.debug("closed front end websocket")
        self._finalized = True


class FrontEndWebSockets(AExitStackMixIn):
    """Maintains a registry of websockets

    Asynchronously sends messages using `send_message` method to respective websockets registered with it
    based on the type of the message
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._msg_router = Router()
        self._msg_queue = asyncio.Queue()
        self._send_loop_task = None

    async def add_websocket(self, type_code, ws):
        fws = self._msg_router.registry.get(type_code)
        if fws is None:
            self._msg_router.register_handler(type_code, fws := FrontEndWebSocket(ws))
            await self._exit_stack.enter_async_context(fws)
            return

        assert isinstance(fws, FrontEndWebSocket)
        await fws.update_transport(ws)

    def send_message(self, message: DataWeaver):
        self._msg_queue.put_nowait(message)

    async def _send_loop(self):
        while True:
            message = await self._msg_queue.get()
            if message is None:
                return
            await self(message)

            logger.debug(f"sent, message to frontend={repr(message)[:30]}")

    async def __call__(self, message: DataWeaver):
        try:
            await self._msg_router(message.type, message)  # noqa
        except KeyError:
            logger.error(f"no handler registered for {message.type} message")
        except TransferIncomplete:
            pass

    async def __aenter__(self):
        self._send_loop_task = asyncio.create_task(self._send_loop(), name="frontend-message-sender")
        await super().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._msg_queue.put_nowait(None)
        await use.safe_cancel_task(self._send_loop_task)

        if not self._msg_queue.empty():
            logger.warning(f"frontend message queue not empty while context manager exit,\
             discarding buffer queue size={self._msg_queue.qsize()}")

        return await self.__aexit__(exc_type, exc_val, exc_tb)


class FrontEndMessagesDispatcher(*Dispatcher):
    """Router messages from frontend to respective handlers"""

    __slots__ = ()

    async def submit(self, data_weaver):
        return await self.call_handler(
            data_weaver.header,
            data_weaver,
            _logger=logger,
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


async def validate_connection(
      frontend_websockets,
      web_socket,
):
    try:
        wire_data = await _asyncio.wait_for(web_socket.recv(), const.SERVER_TIMEOUT)
    except TimeoutError as te:
        logger.error(f"timeout reached, cancelling {web_socket=}")
        await web_socket.close()
        raise ConnectionError from te
    except ConnectionClosedError as cce:
        raise ConnectionError from cce

    verification = DataWeaver(serial_data=wire_data)
    await frontend_websockets.add_websocket(verification.type, web_socket)
    logger.info("verified websocket, waiting for data from websocket")


async def _ui_msg_handler(frontend_websockets, msg_dispatcher):
    async def _handle_ui(web_socket: WebSocketServerProtocol):
        try:
            await validate_connection(frontend_websockets, web_socket)
        except ConnectionError:
            return

        while True:
            data = await web_socket.recv()

            parsed_data = DataWeaver(serial_data=data)
            logger.debug(f"< data from page: {parsed_data=!r}")

            try:
                parsed_data.field_check()
            except InvalidPacket as ip:
                logger.debug("[PAGE HANDLE]", exc_info=ip)
                continue

            if msg_dispatcher.is_registered(parsed_data):
                logger.debug(f"a reply is registered for {parsed_data.msg_id}")
                msg_dispatcher.reply_arrived(parsed_data)
                continue

            msg_dispatcher(parsed_data)

    async def error_wrap(*args, **kwargs):
        try:
            await _handle_ui(*args, **kwargs)
        except websockets.WebSocketException as we:
            logger.exception(f"error occurred in handler exp:{we}", stacklevel=2)

    return error_wrap


@asynccontextmanager
async def start_websocket_server(ui_handler):
    try:
        start_server = await websockets.serve(ui_handler, const.WEBSOCKET_BIND_IP,
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


def _run_page_server(host="localhost", port_page_serve=const.PORT_PAGE_SERVE, exit_stack=None):
    async def _helper():
        with ProcessPoolExecutor(1) as pool:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(pool, _http_server, host, port_page_serve, const.PATH_PAGE)  # noqa

    run_server = asyncio.create_task(_helper(), name="http-demon-for-ui-page")
    if exit_stack:
        exit_stack.push_async_callback(use.safe_cancel_task, run_server)


async def subscribe_to_app_events(
      app_events,
      frontend,
      exit_stack,
):
    await exit_stack.enter_async_context(tg := TaskGroup())
    sub_to_remote_peer_updates(app_events, frontend, tg)


async def init_page_servers(app_config, app_runtime: AppRunTime):
    _run_page_server(port_page_serve=app_config.page_serve_port, exit_stack=app_runtime.exit_stack)
    msg_disp = FrontEndMessagesDispatcher()
    frontend_websockets = FrontEndWebSockets()
    await app_runtime.exit_stack.enter_async_context(
        start_websocket_server(_ui_msg_handler(frontend_websockets, msg_disp))
    )
    await app_runtime.exit_stack.enter_async_context(frontend_websockets)
    return WebFrontend(frontend_websockets, msg_disp)


async def wait_for_profile_selection(frontend: FrontEnd, app_runtime: AppRunTime):
    selected_profile = await align_profiles(frontend)
    return await set_selected_profile(selected_profile)


async def initiate_page_handlers(
      web_frontend: WebFrontend,
      app_config: AppConfig,
      app_runtime: AppRunTime,
):
    from src.conduit import handlesignals, handledata

    handlesignals.register_handlers(
        web_frontend.frontend_messages_dispatcher,
    )

    handledata.register_handlers(
        web_frontend.frontend_messages_dispatcher,
    )

    await subscribe_to_app_events(
        app_runtime.app_events,
        web_frontend,
        app_runtime.exit_stack
    )
