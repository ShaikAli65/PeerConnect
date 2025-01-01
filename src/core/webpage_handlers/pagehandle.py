import asyncio as _asyncio
import importlib
import itertools
from typing import Union

import websockets

try:
    from websockets.asyncio.connection import Connection
except ImportError:
    Connection = None

from src.avails import DataWeaver, StatusMessage, WireData, const, use
from src.avails.exceptions import WebSocketRegistryReStarted
from src.avails.useables import wrap_with_tryexcept
from src.core import Dock

safe_end = Dock.finalizing
PROFILE_WAIT = _asyncio.Event()


class WebSocketRegistry:
    connections: dict[int, Connection] = {}
    message_queue = _asyncio.Queue()
    connections_completed = _asyncio.Event()
    _start_data_sender_task_reference = None
    _started = False

    @classmethod
    def get_websocket(cls, type_id: Union[const.DATA, const.SIGNAL]):
        return cls.connections[type_id]

    @classmethod
    def set_websocket(cls, type_id: Union[const.DATA, const.SIGNAL], websocket):
        cls.connections[type_id] = websocket

    @classmethod
    def send_data(cls, data, type_of_data):
        """
        does not actually send data, adds to a message queue
        """
        cls.message_queue.put_nowait((data, type_of_data))

    @classmethod
    async def start_data_sender(cls):
        if cls._started:
            raise WebSocketRegistryReStarted("reentered registry")
        cls._started = True
        while True:
            data_packet, data_type = await cls.message_queue.get()
            if safe_end.is_set():
                break
            await cls.get_websocket(data_type).send(
                str(data_packet)
            )  # make sure that data is a string
        cls._started = False

    @classmethod
    def clear(cls):
        cls.message_queue.put_nowait((None, None))
        for i in cls.connections.values():
            i.close()
        del cls.connections

    @classmethod
    async def __aenter__(cls):
        f = wrap_with_tryexcept(cls.start_data_sender)
        cls._start_data_sender_task_reference = _asyncio.create_task(f())
        return cls

    @classmethod
    async def __aexit__(cls, exc_type, exc_val, exc_tb):
        cls.clear()
        cls._start_data_sender_task_reference.cancel()
        return True


class ReplyRegistry:
    messages_to_futures_mapping: dict[str, _asyncio.Future] = {}
    id_factory = itertools.count()

    @classmethod
    def register_reply(cls, data: DataWeaver):
        data.id = next(cls.id_factory)
        fut = _asyncio.get_event_loop().create_future()
        cls.messages_to_futures_mapping[data.id] = fut
        return fut

    @classmethod
    def reply_arrived(cls, data: DataWeaver):
        if data.id in cls.messages_to_futures_mapping:
            fut = cls.messages_to_futures_mapping[data.id]
            fut.set_result(data)

    @classmethod
    def is_registered(cls, data: DataWeaver):
        return data.id in cls.messages_to_futures_mapping


def get_verified_type(data: DataWeaver, web_socket):
    WebSocketRegistry.set_websocket(data.header, web_socket)
    if data.match_header(const.DATA):
        print("page data connected")  # debug
        return importlib.import_module("src.core.webpage_handlers.handledata").handler
    if data.match_header(const.SIGNAL):
        print("page signals connected")  # debug
        return importlib.import_module(
            "src.core.webpage_handlers.handlesignals"
        ).handler


async def handle_client(web_socket: Connection):
    try:
        try:
            wire_data = await _asyncio.wait_for(web_socket.recv(), const.SERVER_TIMEOUT)
        except TimeoutError:
            print("timeout reached, cancelling websocket", web_socket)
            await web_socket.close()
            return
        verification = DataWeaver(serial_data=wire_data)
        handle_function = get_verified_type(verification, web_socket)
        print("waiting for data func :", use.func_str(handle_function))

        if handle_function:
            async for data in web_socket:
                use.echo_print("data from page:", data, "\a")
                use.echo_print(f"forwarding to {use.func_str(handle_function)}")
                parsed_data = DataWeaver(serial_data=data)
                if ReplyRegistry.is_registered(parsed_data):
                    ReplyRegistry.reply_arrived(parsed_data)
                    continue
                f = use.wrap_with_tryexcept(handle_function, parsed_data)
                _asyncio.create_task(f())
                if safe_end.is_set():
                    return
        else:
            print("Unknown connection type")
            await web_socket.close()
    except websockets.exceptions.ConnectionClosed:
        print("Websocket Connection closed")


async def start_websocket_server():
    start_server = await websockets.serve(handle_client, "localhost", const.PORT_PAGE)
    use.echo_print(f"websocket server started at ws://{'localhost'}:{const.PORT_PAGE}")
    async with start_server:
        await Dock.finalizing.wait()

    use.echo_print("ending websocket server")


async def initiate_page_handle():
    async with WebSocketRegistry():
        await start_websocket_server()


def dispatch_data(data, expect_reply=False):
    """
    Send data to frontend
    Not actually sends data but queues the :param: data for sending
    Args:
        data (DataWeaver) : data to send
        expect_reply (bool) : if this argument is true then a `asyncio.Future` is returned which can be awaited directly
    Returns:
        bool | asyncio.Future
    """
    if check_closing():
        return False
    print(f"::Sending data to page: {data}")
    WebSocketRegistry.send_data(data, data.type)
    if expect_reply:
        return ReplyRegistry.register_reply(data)
    return True


def send_status_data(data: StatusMessage):
    print(f"::Status update to page: {data}")
    WebSocketRegistry.send_data(data, const.SIGNAL)


def new_message_arrived(message_data: WireData):
    d = DataWeaver(
        header=message_data.header,
        content=message_data["message"],
        _id=message_data.id,
    )
    WebSocketRegistry.send_data(d, const.DATA)


def check_closing():
    if safe_end.is_set():
        use.echo_print("Can't send data to page, safe_end is flip", safe_end)
        return True
    return False
