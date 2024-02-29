import websockets

from core import *
import avails.textobject
import managers.endmanager
from avails import remotepeer
from avails import useables as use
from avails.dataweaver import DataWeaver as datawrap
from managers import filemanager, directorymanager
from core import requests_handler as reqhandler
import core.nomad as nomad

web_socket = None
SafeEnd = asyncio.Event()


async def control_data_flow(data_in: datawrap):
    pass


async def getdata():
    global web_socket, SafeEnd
    while not SafeEnd.is_set():
        # try:
        raw_data = await web_socket.recv()
        data = datawrap(byte_data=raw_data)
        with const.LOCK_PRINT:
            print("data from page:", data)
        await control_data_flow(data_in=data)
        # except Exception as e:
        #     print(f"Error in getdata: {e} at handle.py/getdata() ")
        #     break
    print('::SafeEnd is set')


async def handler(_websocket):
    global web_socket, SafeEnd
    web_socket = _websocket
    if const.USERNAME == '':
        userdata = datawrap(header="thisisacommand",
                            content="no..username", )
        await web_socket.send(userdata.dump())
    else:
        userdata = datawrap(header="thisismyusername",
                            content=f"{const.USERNAME}(^){const.THIS_IP}",
                            _id='0')
        await web_socket.send(userdata.dump())
    const.SAFE_LOCK_FOR_PAGE = True
    const.WEB_SOCKET = web_socket
    const.PAGE_HANDLE_CALL.set()
    await getdata()
    use.echo_print(True,'::handler ended')


def initiate_control():
    use.echo_print(True, '::Initiate_control called at handle.py :', const.PATH_PAGE, const.PAGE_PORT)
    asyncio.set_event_loop(asyncio.new_event_loop())
    start_server = websockets.serve(handler, "localhost", const.PAGE_PORT)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()