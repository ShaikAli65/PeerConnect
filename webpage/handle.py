import websockets
import asyncio
import constants as const
import logs
web_socket: websockets.WebSocketServerProtocol


def send_message(ip:tuple[str,int], text):
    print('send_message --- ', ip, text)

    const.OBJ.send(ip, text)
    return


def send_file(ip, _path):
    _filedata = ''
    print('send_file --- ', ip, _path)
    const.OBJ.send(ip, _filedata)
    return


async def process(_message):
    _message = _message.split('_/!_')
    if _message[0] == 'thisisamessage':
        send_message(*reversed(_message[1].split('~^~')))
    elif _message[0] == 'thisisafile':
        send_file(*reversed(_message[1].split('~^~')))


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
    global web_socket
    web_socket = _websocket
    if const.USERNAME == '':
        await web_socket.send("thisisacommand_/!_no..username".encode(const.FORMAT))
    else:
        await web_socket.send(f"thisismyusername_/!_{const.USERNAME}(^){const.THISIP}".encode(const.FORMAT))
    while True:
        _data = await web_socket.recv()
        print(_data)
        _data = _data.split('_/!_')
        if _data[0] == 'setusername':
            await setname(_data[1])
        else:
            await process(_data[1])


def initiatecontrol():
    asyncio.set_event_loop(asyncio.new_event_loop())
    _startserver = websockets.serve(handler, "localhost", 12346)
    asyncio.get_event_loop().run_until_complete(_startserver)
    asyncio.get_event_loop().run_forever()


def end():
    pass


async def feeduserdata(data):
    global web_socket
    data = f'thisismessage_/!_{data}_/!_{const.USERNAME}(^){const.THISIP}'
    _prerequisites = str(len(data)).encode(const.FORMAT)
    try:
        await web_socket.send(_prerequisites)
        await web_socket.send(data.encode(const.FORMAT))
    except Exception as e:
        logs.errorlog(f"Error sending data: {e}")
    pass


def getdata():
    pass
