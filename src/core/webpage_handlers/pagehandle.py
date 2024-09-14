import asyncio as _asyncio
import importlib
import threading
from typing import Optional, Union

import websockets

import src.avails.constants as const
import src.avails.useables as use
from src.avails.remotepeer import RemotePeer
from src.avails.wire import DataWeaver


PAGE_HANDLE_WAIT = _asyncio.Event()
safe_end = threading.Event()
DATA = 0x00
SIGNAL = 0x01
SOCK_TYPE_DATA = DATA
SOCK_TYPE_SIGNAL = SIGNAL
connections: list[Optional[websockets.WebSocketServerProtocol]] = [None, None]


def get_websocket(type_id: Union[DATA, SIGNAL]):
    global connections
    return connections[type_id]


def _set_websocket(type_id: Union[DATA, SIGNAL], websocket):
    global connections
    connections[type_id] = websocket


def _close_websockets():
    global connections
    for i in connections:
        if i is not None:
            i.close()
    del connections


def get_verified_type(data: DataWeaver, web_socket):
    if data.match_header(SOCK_TYPE_DATA):
        print("page data connected")  # debug
        _set_websocket(SIGNAL, web_socket)
        return importlib.import_module('src.core.webpage_handlers.handledata').handler
    if data.match_header(SOCK_TYPE_SIGNAL):
        print("page signals connected")  # debug
        _set_websocket(DATA, web_socket)
        return importlib.import_module('src.core.webpage_handlers.handlesignals').handler


async def handle_client(web_socket: websockets.WebSocketServerProtocol):
    wire_data = await web_socket.recv()
    verification = DataWeaver(serial_data=wire_data)
    handle_function = get_verified_type(verification, web_socket)
    try:
        print("waiting for data", use.func_str(handle_function))
        if handle_function:
            async for data in web_socket:
                use.echo_print("data from page:", data, '\a')
                use.echo_print(f"forwarding to {use.func_str(handle_function)}")
                await handle_function(data, web_socket)
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
        await PAGE_HANDLE_WAIT.wait()


async def initiate_pagehandle():
    asyncio.create_task(start_websocket_server())  # noqa


def end():
    global PAGE_HANDLE_WAIT
    PAGE_HANDLE_WAIT.set()
    _close_websockets()


def check_closing():
    if safe_end.is_set():
        use.echo_print("Can't send data to page, safe_end is flip", safe_end)
        return True
    return False


async def feed_user_status(peer: RemotePeer):
    if check_closing():
        return
    _data = DataWeaver(header=const.HANDLE_COMMAND,
                       content=peer.username if peer.status else 0,
                       _id=peer.id)

    use.echo_print(f"::signaling page username:{peer.username}\n{_data}")
    await get_websocket(SIGNAL).send(_data.dump())


async def feed_user_data_to_page(_data, ip):
    if check_closing():
        return
    _data = DataWeaver(header="this is a message",
                       content=_data,
                       _id=f"{ip}")
    print(f"::Sending data to page: {ip}\n{_data}")
    await get_websocket(DATA).send(_data.dump())


async def feed_file_data_to_page(_data, _id):
    if check_closing():
        return
    _data = DataWeaver(header=const.HANDLE_FILE_HEADER,
                       content=_data,
                       _id=_id)
    print(f"::Sending data to page: {_id}\n{_data}")
    await get_websocket(DATA).send(_data.dump())
