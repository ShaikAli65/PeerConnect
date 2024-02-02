import websockets
import os
from collections import deque
import avails.textobject
from core import *
import core.nomad as nomad
from avails import remotepeer
from avails.dataweaver import DataWeaver as datawrap

web_socket:websockets.WebSocketServerProtocol = None
server_data_lock = threading.Lock()
SafeEnd = asyncio.Event()
stack_safe = threading.Lock()
focus_user_stack = deque()


async def send_message(content):
    """
    A Wrapper function to function at {nomad.send()}
    Provides Error Handling And Ensures robustness of sending data.

    :param content:
    :return bool:
    """
    if not len(focus_user_stack):
        return False
    try:
        peer_sock: socket.socket = focus_user_stack[0]
        return nomad.send(peer_sock, content)
    except socket.error as exp:
        error_log(f"got error at handle/send_message :{exp}")
        return False


async def send_file(_path):
    """
    :param _path:
    :return bool:
    """
    if not len(focus_user_stack):
        return False
    try:
        peer_remote_obj = focus_user_stack[0]
        return nomad.send(peer_remote_obj, _data=_path, _file_status=True)
    except socket.error as exp:
        error_log(f"got error at handle/send_message :{exp}")
        return False


async def handle_connection(addr_id):
    global focus_user_stack
    if not addr_id:
        return False
    list_of_peer = const.LIST_OF_PEERS
    _nomad: avails.remotepeer = list_of_peer[addr_id]
    if _nomad.status == 0:
        return False
    focus_user_stack.pop() if not len(focus_user_stack) else None
    # peer_soc = socket.socket(const.IP_VERSION, const.PROTOCOL)
    # peer_soc.connect(_nomad.uri)
    focus_user_stack.append(_nomad)
    return True


async def getdata():
    global web_socket
    while not SafeEnd.is_set():
        # try:
        raw_data = await web_socket.recv()
        data = datawrap(byte_data=raw_data)
        with const.PRINT_LOCK:
            print("data from page :", data)
        if data.match(_header=const.HANDLE_COMMAND):
            if data.match(_content=const.HANDLE_END):
                await asyncio.create_task(use.end_session_async())
            # --
            elif data.match(_content=const.HANDLE_CONNECT_USER):
                await handle_connection(addr_id=data.id)
        # --
        elif data.match(_header=const.HANDLE_MESSAGE_HEADER):
            await send_message(content=data.content)
        # --
        elif data.match(_header=const.HANDLE_FILE_HEADER):
            await send_file(_path=data.content)
        # except Exception as webexp:
        #     print('got Exception at handle/getdata():', webexp)
        #     # await asyncio.create_task(main.endSequenceWrapper(0, 0))
        #     break
    return


# @NotInUse
async def set_name(new_username):
    _config_file_path = const.CONFIG_PATH
    const.USERNAME = new_username
    with open(_config_file_path, 'r') as file:
        _lines = file.readlines()

    for i, line in enumerate(_lines):
        if 'username' in line:
            _lines[i] = f'username : {new_username}\n'
            break

    with open(_config_file_path, 'w') as file:
        file.writelines(_lines)


async def handler(_websocket):
    global web_socket, SafeEnd
    web_socket = _websocket
    if const.USERNAME == '':
        userdata = datawrap(header="thisisacommand",
                            content="no..username", )
        await web_socket.send(userdata.dump())
        # print("no username")
    else:
        userdata = datawrap(header="thisismyusername",
                            content=f"{const.USERNAME}(^){const.THIS_IP}",
                            _id='0')
        await web_socket.send(userdata.dump())
    const.SAFE_LOCK_FOR_PAGE = True
    const.WEB_SOCKET = web_socket
    const.PAGE_HANDLE_CALL.set()
    await getdata()
    with const.PRINT_LOCK:
        print('::handler ended')


def initiate_control():
    with const.PRINT_LOCK:
        print('::Initiate_control called at handle.py :', const.PAGE_PATH, const.PAGE_PORT)
    os.system(f'cd {const.PAGE_PATH} && index.html')
    asyncio.set_event_loop(asyncio.new_event_loop())
    start_server = websockets.serve(handler, "localhost", const.PAGE_PORT)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()


async def feed_user_data(_data: avails.textobject.PeerText, ip):
    global web_socket
    _data = datawrap(header="thisismessage",
                     content=f"{_data.decode()}",
                     _id=f"{_data.id}")
    try:
        print(f"::Sending data :{_data} \n to page: {ip}")
        await web_socket.send(_data.dump())
    except Exception as e:
        error_log(f"Error sending data handle.py/feed_user_data exp: {e}")
        return
    pass


async def feed_server_data(peer: avails.remotepeer.RemotePeer):
    global web_socket, server_data_lock
    with server_data_lock:
        _data = datawrap(header=const.HANDLE_COMMAND,
                         content=peer.username,
                         _id=peer.id)
        try:
            with const.PRINT_LOCK:
                print(f"::Sending data :{_data} \nto page: {peer.username}")
            await const.WEB_SOCKET.send(_data.dump())

        except Exception as e:
            error_log(f"Error sending data at handle.py/feed_server_data, exp: {e}")
        pass


async def end():
    global SafeEnd, web_socket
    if web_socket is None:
        return None
    SafeEnd.set()
    asyncio.get_event_loop().stop()
    await web_socket.close()
    with const.PRINT_LOCK:
        time.sleep(const.anim_delay)
        print('::Page Disconnected Successfully')
    pass
