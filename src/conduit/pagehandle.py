"""
This is Frontend, Frontend is This
Interfacing with UI using websockets

"""

import asyncio
import asyncio as _asyncio
import logging
import sys
from asyncio import TaskGroup
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import wraps
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from src.avails import BaseDispatcher, Router, const, use
from src.avails.exceptions import InvalidPacket, TransferIncomplete
from src.avails.mixins import AExitStackMixIn, CallHandlerMixIn, ReplyRegistryMixIn, TaskGroupMixIn
from src.conduit.app_event_subs import sub_to_messages, sub_to_remote_peer_updates, sub_to_transfer_updates
from src.conduit.bases import FrontEnd
from src.conduit.frontend_web import WebFrontend
from src.conduit.handleprofiles import align_profiles, set_selected_profile
from src.conduit.ui_codec import DataWeaver
from src.configurations.appconfig import AppRunTime
from src.net.msg_socket import MessageSocket
from websockets import ConnectionClosedError, WebSocketException, WebSocketServerProtocol, serve

logger = logging.getLogger(__name__)


class FrontEndWebSockets(AExitStackMixIn):
    """Maintains a registry of websockets

    Asynchronously sends messages using `send_message` method to respective websockets registered with it
    based on the type of the message
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._msg_router = Router[MessageSocket]()
        self._msg_queue = asyncio.Queue()
        self._send_loop_task = None

    async def add_websocket(self, type_code, ws):
        fws = self._msg_router.registry.get(type_code)
        if fws is None:
            self._msg_router.register_handler(
                type_code,
                fws := MessageSocket(transport=ws)
            )
            await self._exit_stack.enter_async_context(fws.context_manager())
            return

        assert isinstance(ws, WebSocketServerProtocol)
        await fws.update_transport(ws)

    def send_message(self, message: DataWeaver):
        self._msg_queue.put_nowait(message)

    async def _send_loop(self):
        while True:
            message = await self._msg_queue.get()
            if message is None:
                break
            await self(message)

            logger.debug(f"sent, message to frontend={repr(message)[:30]}")

        logger.debug("exiting frontend message sender")

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
        # await use.safe_cancel_task(self._send_loop_task)
        await self._send_loop_task

        if not self._msg_queue.empty():
            logger.warning(f"frontend message queue not empty while context manager exit,\
             discarding buffer queue size={self._msg_queue.qsize()}")

        return await super().__aexit__(exc_type, exc_val, exc_tb)


class FrontEndMessagesDispatcher(
    TaskGroupMixIn,
    ReplyRegistryMixIn,
    CallHandlerMixIn,
    BaseDispatcher
):
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


def _ui_msg_handler(frontend_websockets, msg_dispatcher):
    async def handle_ui(web_socket: WebSocketServerProtocol):
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

    @wraps(handle_ui)
    async def error_wrap(*args, **kwargs):
        try:
            await handle_ui(*args, **kwargs)
        except WebSocketException as we:
            logger.exception(f"error occurred in handler exp:{we}", stacklevel=2)

    return error_wrap


@asynccontextmanager
async def start_websocket_server(ui_handler):
    try:
        start_server = await serve(ui_handler, const.WEBSOCKET_BIND_IP,
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


def _run_page_server(host="localhost", port_page_serve=const.PORT_PAGE_SERVE, exit_stack=None):
    class HTTPServer(ThreadingHTTPServer):
        def finish_request(self, request, client_address):
            self.RequestHandlerClass(request, client_address, self, directory=const.PATH_PAGE)  # noqa

    httpd = HTTPServer((host, port_page_serve), SimpleHTTPRequestHandler)

    def _http_server(*args, **kwargs):
        with httpd:
            host, port = httpd.socket.getsockname()[:2]
            url_host = f'[{host}]' if ':' in host else host
            logger.info(
                f"Serving HTTP on {host} port {port} "
                f"(http://{url_host}:{port}/) ..."
            )
            httpd.serve_forever()
            logger.info("HTTP server stopped.")

    def _close_http_server(*args, **kwargs):
        assert args == () and kwargs == {}, f"not expecting any args, {args=} {kwargs=}"
        logger.debug("calling shutdown")
        httpd.server_close()
        httpd.shutdown()
        logger.debug("calling shutdown done")

    async def _helper():
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="http-deamon-thread") as th:
            try:
                await loop.run_in_executor(th, _http_server)
            finally:
                # has to be ran in a different thread, otherwise it will deadlock
                await loop.run_in_executor(th, _close_http_server)

    use.long_running_task(_helper(), "http-server", exit_stack)


async def subscribe_to_app_events(
      app_events,
      frontend,
      exit_stack,
):
    await exit_stack.enter_async_context(tg := TaskGroup())
    sub_to_remote_peer_updates(app_events, frontend, tg)
    sub_to_transfer_updates(app_events, frontend, tg)
    sub_to_messages(app_events, frontend, tg)


async def init_page_servers(app_config, app_runtime: AppRunTime):
    _run_page_server(port_page_serve=app_config.page_serve_port, exit_stack=app_runtime.exit_stack)
    msg_disp = FrontEndMessagesDispatcher()
    frontend_websockets = FrontEndWebSockets()
    await app_runtime.exit_stack.enter_async_context(msg_disp)
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
      conn_service,
      msg_service,
      peer_service,
      app_runtime: AppRunTime,
):
    from src.conduit import handlesignals, handledata

    for event, handler in handlesignals.handlers_to_register(conn_service, msg_service, web_frontend):
        web_frontend.frontend_messages_dispatcher.register_handler(event.event_name(), handler)

    for event, handler in handledata.handlers_to_register(peer_service, web_frontend):  # TODO: fix this
        web_frontend.frontend_messages_dispatcher.register_handler(event.event_name(), handler)

    await subscribe_to_app_events(
        app_runtime.app_events,
        web_frontend,
        app_runtime.exit_stack
    )
