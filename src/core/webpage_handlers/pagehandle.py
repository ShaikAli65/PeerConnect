import asyncio
import importlib
import threading
from typing import Optional

import websockets

import src.avails.constants as const
import src.avails.useables as use
from src.avails.remotepeer import RemotePeer
from src.avails.wire import DataWeaver

main_loop = asyncio.new_event_loop()
safe_end = threading.Event()
DATA = 0x00
SIGNAL = 0x01
SOCK_TYPE_DATA = DATA
SOCK_TYPE_SIGNAL = SIGNAL
connections: list[Optional[websockets.WebSocketServerProtocol]] = [None, None]


def get_verified_type(data: DataWeaver, web_socket):
    if data.match_header(SOCK_TYPE_DATA):
        print("page data connected")  # debug
        connections[DATA] = web_socket
        return importlib.import_module('src.core.webpage_handlers.handledata').handler
    if data.match_header(SOCK_TYPE_SIGNAL):
        print("page signals connected")  # debug
        connections[SIGNAL] = web_socket
        return importlib.import_module('src.core.webpage_handlers.handlesignals').handler


async def handle_client(web_socket: websockets.WebSocketServerProtocol):
    wire_data = await web_socket.recv()
    verification = DataWeaver(serial_data=wire_data)
    handle_function = get_verified_type(verification, web_socket)
    print("waiting for data", use.func_str(handle_function))
    if handle_function:
        async for data in web_socket:
            use.echo_print("data from page:", data, '\a')
            handle_function(data, web_socket)
            if safe_end.is_set():
                return
    else:
        print("Unknown connection type")
        await web_socket.close()
    try:
        ...
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed")


async def start_websocket_server():
    from src import core
    start_server = await websockets.serve(handle_client, const.THIS_IP, const.PORT_PAGE)
    use.echo_print(f"websocket server started at ws://{const.THIS_IP}:{const.PORT_PAGE}")
    async with start_server:
        await core.PAGE_HANDLE_WAIT.wait()


async def initiate_pagehandle():
    asyncio.create_task(start_websocket_server())  # noqa


def end():
    global main_loop
    if main_loop.is_running():
        main_loop.stop()
        main_loop.close()
    safe_end.set()
    safe_end.clear()


def check_closing():
    if safe_end.is_set():
        use.echo_print("Can't send data to page, safe_end is flip", safe_end)
        return True
    return False


def _send_data(websocket, data):
    async def _async_send_wrapper(_websocket):
        await _websocket.send(data)

    global main_loop
    asyncio.run_coroutine_threadsafe(_async_send_wrapper(websocket), main_loop)


def feed_user_status(peer: RemotePeer):
    if check_closing():
        return
    _data = DataWeaver(header=const.HANDLE_COMMAND,
                       content=peer.username if peer.status else 0,
                       _id=peer.id)
    use.echo_print(f"::signaling page username:{peer.username}\n{_data}")
    _send_data(connections[SIGNAL], _data)


async def feed_user_data_to_page(_data, ip):
    if check_closing():
        return
    _data = DataWeaver(header="this is a message",
                       content=_data,
                       _id=f"{ip}")
    print(f"::Sending data to page: {ip}\n{_data}")
    _send_data(connections[DATA], _data)


async def feed_file_data_to_page(_data, _id):
    if check_closing():
        return
    _data = DataWeaver(header=const.HANDLE_FILE_HEADER,
                       content=_data,
                       _id=_id)
    print(f"::Sending data to page: {_id}\n{_data}")
    _send_data(connections[DATA], _data)

if __name__ == '__main__':
    asyncio.run(initiate_pagehandle())
