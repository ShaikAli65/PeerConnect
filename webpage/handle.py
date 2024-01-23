import websockets
import os
from collections import deque
import avails.textobject
from core import *
import main
import core.nomad as nomad
from avails import  remotepeer

web_socket: websockets.WebSocketServerProtocol
serverdatalock = threading.Lock()
SafeEnd = asyncio.Event()
stacksafe = threading.Lock()
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
        errorlog(f"got error at handle/send_message :{exp}")
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
        return nomad.send(peer_remote_obj,_data=_path,filestatus=True)
    except socket.error as exp:
        errorlog(f"got error at handle/send_message :{exp}")
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
        _data = json.loads(raw_data)
        print("data from page :", _data)
        _data_header = _data['header']
        _data_content = _data['content']
        _data_id = _data['id']
        if _data_header == const.HANDLE_COMMAND:
            if _data_content == const.HANDLE_END:
                await asyncio.create_task(main.endsession(0, 0))
            # --
            elif _data_content == const.HANDLE_CONNECT_USER:
                await handle_connection(addr_id=_data_id)
        # --
        elif _data_header == const.HANDLE_MESSAGE_HEADER:
            await send_message(content=_data_content)
        # --
        elif _data_header == const.HANDLE_FILE_HEADER:
            await send_file(_path=_data_content)
        # except Exception as webexp:
        #     print('got Exception at handle/getdata():', webexp)
        #     # await asyncio.create_task(main.endsession(0, 0))
        #     break
    return


@NotInUse
async def setname(new_username):
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
        await web_socket.send("thisisacommand_/!_no..username".encode(const.FORMAT))
        print("no username")
    else:
        userdata = f"thisismyusername_/!_{const.USERNAME}(^){const.THIS_IP}".encode(const.FORMAT)
        await web_socket.send(userdata.decode(const.FORMAT))
    const.SAFE_LOCK_FOR_PAGE = True
    const.WEB_SOCKET = web_socket
    const.HANDLE_CALL.set()
    await getdata()
    print('::handler ended')


def initiatecontrol():
    print('::Initiatecontrol called at handle.py :', const.PAGE_PATH, const.PAGE_PORT)
    os.system(f'cd {const.PAGE_PATH} && index.html')
    asyncio.set_event_loop(asyncio.new_event_loop())
    _startserver = websockets.serve(handler, "localhost", const.PAGE_PORT)
    asyncio.get_event_loop().run_until_complete(_startserver)
    asyncio.get_event_loop().run_forever()


async def feed_user_data(data: avails.textobject.PeerText, ip: tuple = tuple()):
    global web_socket
    data = {
        "header": "thisismessage",
        "content": f"{data.decode()}",
        "id": f"{data.id}",
    }
    try:
        await web_socket.send(json.dumps(data))
    except Exception as e:
        # logs.errorlog(f"Error sending data: {e}")
        print(f"handle.py line 83 Error sending data: {e}")
        return
    pass


async def feed_server_data(peer:avails.remotepeer.RemotePeer):
    global web_socket, serverdatalock
    with serverdatalock:
        _data = {
            'header':const.HANDLE_COMMAND,
            'content':peer.username,
            'id':peer.id
        }
        serialized_data = json.dumps(_data)

        # print("data :", data)
        try:
            await const.WEB_SOCKET.send(_data)

        except Exception as e:
            # logs.errorlog(f"Error sending data: {e}")
            print(f" handle.py line 97 Error sending data: {e}")
        pass


async def end():
    global SafeEnd, web_socket
    SafeEnd.set()
    print('::Page Disconnected Successfully')
    asyncio.get_event_loop().stop()
    await web_socket.close() if web_socket else None
    pass
