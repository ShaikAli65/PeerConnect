import websockets


from src.configurations.boot_up import launch_web_page
from src.core import *
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.webpage_handlers.handle_profiles import align_profiles

web_socket: websockets.WebSocketServerProtocol
safe_end = asyncio.Event()


async def control_data_flow(data_in: DataWeaver):
    if data_in.header == "":
        pass
    pass


async def getdata():
    global web_socket, safe_end
    while not safe_end.is_set():
        # try:
        raw_data = await web_socket.recv()
        data = DataWeaver(byte_data=raw_data)
        use.echo_print("data from page:", data)
        await control_data_flow(data_in=data)
        # except Exception as e:
        #     print(f"Error in getdata: {e} at handle_data_flow.py/getdata() ")
        #     break
    print('::SafeEnd is flip')


async def handler(_websocket):
    global web_socket, safe_end
    web_socket = _websocket
    try:
        await align_profiles(_websocket)
    except websockets.exceptions.ConnectionClosedOK:
        end()
    await getdata()
    use.echo_print('::handler ended')


def initiate_control():
    use.echo_print('::Initiate_control called at handle_signals.py :', const.PATH_PAGE, const.PORT_PAGE_SIGNALS)
    launch_web_page()
    asyncio.set_event_loop(asyncio.new_event_loop())
    start_server = websockets.serve(handler, "localhost", const.PORT_PAGE_SIGNALS)
    # start_server = websockets.serve(handler, "172.16.197.166", const.PORT_PAGE_SIGNALS)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()


def end():
    global safe_end, web_socket
    safe_end.set()
    const.END_OR_NOT = True
    web_socket.close() if web_socket else None
    web_socket.ws_server.close()
    asyncio.get_event_loop().stop() if asyncio.get_event_loop().is_running() else asyncio.get_event_loop().close()
    loop = asyncio.get_running_loop()
    loop.stop()

    const.HOLD_PROFILE_SETUP.set()
    use.echo_print("::Handle_signals Ended")
