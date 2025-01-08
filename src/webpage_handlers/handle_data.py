import asyncio
import sys

import websockets.server

import src.avails.textobject
import src.core.senders
import src.managers.endmanager

from src.core.senders import *
from src.avails.remotepeer import RemotePeer
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.core import requests_handler as req_handler
from src import avails

loop: asyncio.events = asyncio.new_event_loop()
web_socket: websockets.WebSocketServerProtocol
server_data_lock = threading.Lock()
safe_end = asyncio.Event()
stack_safe: threading.Lock = threading.Lock()


def handle_connection(addr_id):
    try:
        _nomad: RemotePeer = peer_list.get_peer(addr_id)

    except KeyError:
        print("Looks like the user is not in the list can't connect to the user", peer_list)
        return False
    RecentConnections.connect_peer(_nomad)


def command_flow_handler(data_in: DataWeaver):
    if data_in.match_content(const.HANDLE_END):
        safe_end.set()
        src.managers.endmanager.end_session()
        exit(1)
    elif data_in.match_content(const.HANDLE_CONNECT_USER):
        handle_connection(addr_id=data_in.id)
    elif data_in.match_content(const.HANDLE_OPEN_FILE):
        use.open_file(data_in.content)
    elif data_in.match_header(const.HANDLE_RELOAD):
        use.reload_protocol()
        return
    elif data_in.match_header(const.HANDLE_SYNC_USERS):
        use.start_thread(_target=req_handler.sync_list)


async def control_data_flow(data_in: DataWeaver):
    """
    A function to control the data flow from the page
    :param data_in:

    :return:
    """
    function_map = {
        const.HANDLE_COMMAND: lambda x: command_flow_handler(x),
        const.HANDLE_MESSAGE_HEADER: lambda x: sendMessage(x),
        const.HANDLE_FILE_HEADER: lambda x: sendFile(x),
        const.HANDLE_DIR_HEADER: lambda x: sendDir(x),
    }
    try:
        function_map.get(data_in.header, lambda x: None)(data_in)
    except TypeError as exp:
        error_log(f"Error at handle/control_data_flow : {exp} due to {data_in.header}")


async def getdata():
    global web_socket, safe_end
    while not safe_end.is_set():
        # try:
        raw_data = await web_socket.recv()
        data = DataWeaver(byte_data=raw_data)
        use.echo_print("data from page:\n", data)
        await control_data_flow(data_in=data)
        # except Exception as e:
        #     print(f"Error in getdata: {e} at handle_data_flow.py/getdata() ")
        #     break
    print('::SafeEnd is flip')


async def handler(_websocket):
    global web_socket, safe_end
    web_socket = _websocket
    const.HOLD_PROFILE_SETUP.wait()
    if const.USERNAME == '':
        userdata = DataWeaver(header="this is a command",
                              content="no..username", )
    else:
        userdata = DataWeaver(header="this is my username",
                              content=f"{const.USERNAME}(^){const.THIS_IP}",
                              _id='0')
    await web_socket.send(userdata.dump())
    verification = DataWeaver(byte_data=await web_socket.recv())
    if verification.header == const.HANDLE_VERIFICATION:
        await asyncio.sleep(0.2)  # time to load page's javascript
        for peer in peer_list.peers():
            await feed_user_status_to_page(peer)
    use.echo_print("::sent list of peers to page")
    const.WEB_SOCKET = web_socket
    const.PAGE_HANDLE_CALL.set()
    await getdata()
    use.echo_print('::handler_data ended')


def initiate_control():
    async def _helper():
        global loop
        loop = asyncio.get_event_loop()
        start_server = websockets.serve(handler, "localhost", const.PORT_PAGE_DATA,)
        async with start_server:
            await safe_end.wait()

    asyncio.run(_helper())


async def feed_user_data_to_page(_data, ip):
    if safe_end.is_set():
        use.echo_print("Can't send data to page, safe_end is flip", safe_end)
        return
    global web_socket
    _data = DataWeaver(header="this is a message",
                       content=_data,
                       _id=f"{ip}")
    # try:
    print(f"::Sending data to page: {ip}\n{_data}")
    await web_socket.send(_data.dump())
    # except Exception as e:
    #     error_log(f"Error sending data handle_data_flow.py/feed_user_data exp: {e}")
    #     return


async def feed_file_data_to_page(_data, _id):
    if safe_end.is_set():
        use.echo_print("Can't send data to page, safe_end is flip", safe_end)
        return
    global web_socket
    _data = DataWeaver(header=const.HANDLE_FILE_HEADER,
                       content=_data,
                       _id=_id)
    # try:
    print(f"::Sending data to page: {_id}\n{_data}")
    await web_socket.send(_data.dump())
    # except Exception as e:
    #     error_log(f"Error sending data handle_data_flow.py/feed_file_data exp: {e}")
    #     return


async def feed_user_status_to_page(peer: avails.remotepeer.RemotePeer):
    if safe_end.is_set():
        use.echo_print("Can't send data to page, safe_end is flip", safe_end)
        return
    global web_socket, server_data_lock
    with server_data_lock:
        _data = DataWeaver(header=const.HANDLE_COMMAND,
                           content=peer.username if peer.status else 0,
                           _id=peer.id)
        # try:
        use.echo_print(f"::signaling page username:{peer.username}\n{_data}")
        try:
            await web_socket.send(_data.dump())
        except websockets.exceptions.ConnectionClosedError:
            pass


async def end():
    global loop, web_socket
    safe_end.set()
    await web_socket.close()
    web_socket.ws_server.close()
    if loop.is_running():
        loop.call_soon_threadsafe(loop.stop)
    # Immediately stop the loop without waiting for tasks to complete
    loop.stop()
    # Force close the loop
    print("::Handle_data Ended")
    sys.exit(1)
