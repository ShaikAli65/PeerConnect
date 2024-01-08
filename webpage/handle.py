import websockets
import json

import core.textobject
from core import *
import main
import core.nomad as nomad
web_socket: websockets.WebSocketServerProtocol
serverdatalock = threading.Lock()
SafeEnd = asyncio.Event()


def send_message(text, ip):
    print('send_message --- ', ip, text)
    ip = eval(ip)
    if nomad.send(ip, text):
        print('sent msg successfully')
    return


def send_file(_path, ip):
    print('send_file --- ', ip, _path)
    ip = eval(ip)
    return nomad.send_file(ip, _path)


async def getdata():
    global web_socket
    while not SafeEnd.is_set():
        try:
            _data = await web_socket.recv()
            print("data from page :", _data)
            _data = _data.split('_/!_')
            if _data[0] == 'thisisamessage':
                send_message(*_data[1].split('~^~'))
            elif _data[0] == 'thisisafile':
                send_file(*_data[1].split('~^~'))
            elif _data[0] == 'thisisacommand':
                if _data[1] == 'endprogram':
                    await asyncio.create_task(main.endsession(0, 0))
                if _data[1] == 'connectuser':
                    pass
        except Exception as webexp:
            print('got Exception at getdata():', webexp)
            await asyncio.create_task(main.endsession(0, 0))
            break
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
    print('handler ended')


def initiatecontrol():
    print('::Initiatecontrol called at handle.py :', const.PAGEPATH, const.PAGEPORT)
    os.system(f'cd {const.PAGEPATH} && index.html')
    asyncio.set_event_loop(asyncio.new_event_loop())
    _startserver = websockets.serve(handler, "localhost", const.PAGEPORT)
    asyncio.get_event_loop().run_until_complete(_startserver)
    asyncio.get_event_loop().run_forever()


async def feeduserdata(data: core.textobject.PeerText, ip: tuple = tuple()):
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


async def feedserverdata(peer):
    global web_socket, serverdatalock
    with serverdatalock:
        _ip = peer.uri[0]
        _port = peer.uri[1]
        data = f'thisisacommand_/!_{peer.status}_/!_{peer.username}(^){_ip}~{_port}'
        # print("data :", data)
        try:
            await const.WEBSOCKET.send(data)
        except Exception as e:
            # logs.errorlog(f"Error sending data: {e}")
            print(f" handle.py line 97 Error sending data: {e}")
        pass


async def end():
    global SafeEnd, web_socket
    SafeEnd.set()
    print('::Page Disconnected Successfully')
    asyncio.get_event_loop().stop()
    await web_socket.close()
    pass
