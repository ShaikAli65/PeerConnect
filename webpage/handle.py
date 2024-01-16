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
        peer_sock: socket.socket = focus_user_stack[0]
        return nomad.send(peer_sock,_data=_path,filestatus=True)
    except socket.error as exp:
        errorlog(f"got error at handle/send_message :{exp}")
        return False


async def handle_connection(addr_id):
    global focus_user_stack
    if not addr_id:
        return False
    list_of_peer = const.LISTOFPEERS
    _nomad: avails.remotepeer = list_of_peer[addr_id]
    if _nomad.status == 0:
        return False
    focus_user_stack.pop() if not len(focus_user_stack) else None
    peer_soc = socket.socket(const.IPVERSION, const.PROTOCOL)
    peer_soc.connect(_nomad.uri)
    focus_user_stack.append(peer_soc)
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
        if _data_header == const.HANDLECOMMAND:
            if _data_content == const.HANDLEND:
                await asyncio.create_task(main.endsession(0, 0))
            # --
            elif _data_content == const.HANDLECONNECTUSER:
                await handle_connection(addr_id=_data_id)
        # --
        elif _data_header == const.HANDLEMESSAGEHEADER:
            await send_message(content=_data_content)
        # --
        elif _data_header == const.HANDLEFILEHEADER:
            await send_file(_path=_data_content)
        # except Exception as webexp:
        #     print('got Exception at handle/getdata():', webexp)
        #     # await asyncio.create_task(main.endsession(0, 0))
        #     break
    return


@NotInUse
async def setname(new_username):
    _config_file_path = const.CONFIGPATH
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
        userdata = f"thisismyusername_/!_{const.USERNAME}(^){const.THISIP}".encode(const.FORMAT)
        await web_socket.send(userdata.decode(const.FORMAT))
    const.SAFELOCKFORPAGE = True
    const.WEBSOCKET = web_socket
    const.HANDLECALL.set()
    await getdata()
    print('::handler ended')


def initiatecontrol():
    print('::Initiatecontrol called at handle.py :', const.PAGEPATH, const.PAGEPORT)
    os.system(f'cd {const.PAGEPATH} && index.html')
    asyncio.set_event_loop(asyncio.new_event_loop())
    _startserver = websockets.serve(handler, "localhost", const.PAGEPORT)
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


async def feed_server_data(peer):
    global web_socket, serverdatalock
    with serverdatalock:
        _ip = peer.uri[0]
        _port = peer.uri[1]
        _data = f'thisisacommand_/!_{peer.status}_/!_{peer.username}(^){_ip}~{_port}'
        """
        _data = {
            'header':const.HANDLECOMMAND,
            'content':peer.username,
            'id':peer.id             
        }
        
        serialized_data = json.dumps(_data)
        
        """
        # print("data :", data)
        try:
            await const.WEBSOCKET.send(_data)

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
