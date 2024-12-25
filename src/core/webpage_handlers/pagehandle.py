import asyncio as _asyncio
import importlib
import itertools
from typing import Optional, Union

import websockets

from src.avails import DataWeaver, StatusMessage, WireData, const, use
from src.avails.useables import wrap_with_tryexcept
from src.core import Dock

safe_end = Dock.finalizing
PROFILE_WAIT = _asyncio.Event()

DATA = 0x00
SIGNAL = 0x01


class WebSocketRegistry:
    SOCK_TYPE_DATA = DATA
    SOCK_TYPE_SIGNAL = SIGNAL
    connections: list[Optional[websockets.WebSocketServerProtocol]] = [None, None]
    message_queue = _asyncio.Queue()
    connections_completed = _asyncio.Event()
    _start_data_sender_task_reference = None

    @classmethod
    def get_websocket(cls, type_id: Union[DATA, SIGNAL]):
        return cls.connections[type_id]

    @classmethod
    def set_websocket(cls, type_id: Union[DATA, SIGNAL], websocket):
        cls.connections[type_id] = websocket

    @classmethod
    def send_data(cls, data, type_of_data):
        """
        does not actually send data, adds to a message queue
        """
        cls.message_queue.put((data, type_of_data))

    @classmethod
    async def start_data_sender(cls):
        while True:
            data_packet, data_type = await cls.message_queue.get()
            if safe_end.is_set():
                return
            await cls.get_websocket(data_type).send(str(data_packet))  # make sure that data is a string

    @classmethod
    def clear(cls):
        cls.message_queue.put_nowait((None, None))
        for i in cls.connections:
            if i is not None:
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


def get_verified_type(data: DataWeaver, web_socket):
    if data.match_header(WebSocketRegistry.SOCK_TYPE_DATA):
        print("page data connected")  # debug
        WebSocketRegistry.set_websocket(SIGNAL, web_socket)
        return importlib.import_module('src.core.webpage_handlers.handledata').handler
    if data.match_header(WebSocketRegistry.SOCK_TYPE_SIGNAL):
        print("page signals connected")  # debug
        WebSocketRegistry.set_websocket(DATA, web_socket)
        return importlib.import_module('src.core.webpage_handlers.handlesignals').handler


async def handle_client(web_socket: websockets.WebSocketServerProtocol):
    try:
        wire_data = await web_socket.recv()
        verification = DataWeaver(serial_data=wire_data)
        handle_function = get_verified_type(verification, web_socket)
        print("waiting for data", use.func_str(handle_function))
        if handle_function:
            async for data in web_socket:
                use.echo_print("data from page:", data, '\a')
                use.echo_print(f"forwarding to {use.func_str(handle_function)}")
                parsed_data = DataWeaver(serial_data=data)
                if parsed_data.is_reply:
                    ReplyRegistry.reply_arrived(parsed_data)
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
    start_server = await websockets.serve(handle_client, const.THIS_IP, const.PORT_PAGE)
    use.echo_print(f"websocket server started at ws://{const.THIS_IP}:{const.PORT_PAGE}")
    async with start_server:
        await Dock.finalizing.wait()
        
    use.echo_print("ending websocket server")


async def initiate_pagehandle():
    f = use.wrap_with_tryexcept(WebSocketRegistry.start_data_sender)
    _asyncio.create_task(f())

    async with WebSocketRegistry():
        await start_websocket_server()
    print("3al;pksdfnoidsabnfgibgiuferqbguerbguiobedguertbnu")


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
    if expect_reply:
        return ReplyRegistry.register_reply(data)
    WebSocketRegistry.send_data(data, data.type)
    return True


def send_status_data(data: StatusMessage):
    print(f"::Status update to page: {data}")
    WebSocketRegistry.send_data(data, SIGNAL)


def new_message_arrived(message_data: WireData):
    d = DataWeaver(
        header=message_data.header,
        content=message_data['message'],
        _id=message_data.id,
    )
    WebSocketRegistry.send_data(d, DATA)


def check_closing():
    if safe_end.is_set():
        use.echo_print("Can't send data to page, safe_end is flip", safe_end)
        return True
    return False
