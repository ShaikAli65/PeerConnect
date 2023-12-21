import websockets
import asyncio
import threading


from core import constants as const
from core.main import NotInUse
from logs import *
from avails import *


web_socket: websockets.WebSocketServerProtocol
serverdatalock = threading.Lock()


def send_message(ip:tuple[str,int], text):
    print('send_message --- ', ip, text)

    const.OBJ.send(ip, text)
    return


def send_file(ip, _path):
    _filedata = ''
    print('send_file --- ', ip, _path)
    const.OBJ.send(ip, _filedata)
    return


async def getdata():
    global web_socket
    _data = await web_socket.recv()
    print("data from page :", _data)
    _data = _data.split('_/!_')
    if _data[0] == 'thisisamessage':
        send_message(*reversed(_data[1].split('~^~')))
    elif _data[0] == 'thisisafile':
        send_file(*reversed(_data[1].split('~^~')))
    pass


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


async def handler(_websocket, port):
    print('handler called')
    global web_socket
    web_socket = _websocket
    if const.USERNAME == '':
        await web_socket.send("thisisacommand_/!_no..username".encode(const.FORMAT))
        print("no username")
    else:
        userdata = f"thisismyusername_/!_{const.USERNAME}(^){const.THISIP}".encode(const.FORMAT)
        await web_socket.send(userdata.decode(const.FORMAT))
        print("username sent")
    while True:
        await getdata()


def initiatecontrol():
    print('initiatecontrol called')
    asyncio.set_event_loop(asyncio.new_event_loop())
    _startserver = websockets.serve(handler, "localhost", 12347)
    asyncio.get_event_loop().run_until_complete(_startserver)
    asyncio.get_event_loop().run_forever()


async def feeduserdata(data):
    global web_socket
    data = f'thisismessage_/!_{data}(^){const.THISIP}'
    try:
        await web_socket.send(data)
    except Exception as e:
        # logs.errorlog(f"Error sending data: {e}")
        print(f"handle.py line 83 Error sending data: {e}")
    pass


async def feedserverdata(peer,status):
    global web_socket,serverdatalock
    with serverdatalock:
        _ip = peer.uri[0]
        _port = peer.uri[1]
        data = f'thisisacommand_/!_{status}_/!_{peer.username}(^){_ip}:{_port}'
        print("data :",data)
        try:
            await web_socket.send(data)
        except Exception as e:
            # logs.errorlog(f"Error sending data: {e}")
            print(f" handle.py line 97 Error sending data: {e}")
        pass


def end():
    pass
