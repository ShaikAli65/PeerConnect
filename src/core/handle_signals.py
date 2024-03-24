import websockets
import webbrowser
from src.core import *
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.managers.profile_manager import all_profiles, set_selected_profile, ProfileManager

web_socket: websockets.WebSocketServerProtocol
SafeEnd = asyncio.Event()


async def control_data_flow(data_in: DataWeaver):
    if data_in.header == "":
        pass
    pass


async def getdata():
    global web_socket, SafeEnd
    while not SafeEnd.is_set():
        # try:
        raw_data = await web_socket.recv()
        data = DataWeaver(byte_data=raw_data)
        use.echo_print(False, "data from page:", data)
        await control_data_flow(data_in=data)
        # except Exception as e:
        #     print(f"Error in getdata: {e} at handle_data_flow.py/getdata() ")
        #     break
    print('::SafeEnd is set')


async def handler(_websocket):
    global web_socket, SafeEnd
    web_socket = _websocket
    try:
        await align_profiles(_websocket)
    except websockets.exceptions.ConnectionClosedOK:
        end()
    await getdata()
    use.echo_print(True, '::handler ended')


def initiate_control():
    use.echo_print(True, '::Initiate_control called at handle_signals.py :', const.PATH_PAGE, const.PORT_PAGE_SIGNALS)
    webbrowser.open(os.path.join(const.PATH_PAGE, "index.html"))
    asyncio.set_event_loop(asyncio.new_event_loop())
    start_server = websockets.serve(handler, "localhost", const.PORT_PAGE_SIGNALS)
    # start_server = websockets.serve(handler, "172.16.197.166", const.PORT_PAGE_SIGNALS)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()


# ----------------------------------------------------profile handlers---------------------------------------------------------------

async def send_profiles(_websocket):
    # load_profiles_to_program()
    userdata = DataWeaver(header="this is a profiles list",
                          content=all_profiles())
    await web_socket.send(userdata.dump())
    use.echo_print(False, '::profiles sent')


async def align_profiles(_websocket):
    await send_profiles(_websocket)
    profile_data = await get_selected_profile()
    profile_object = use.get_profile_from_username(next(iter(profile_data.keys())))
    for header, content in profile_data[profile_object.username].items():
        profile_object.edit_profile(header, content)
    set_selected_profile(profile_object)
    const.HOLD_PROFILE_SETUP.set()
    # await configure_further_profile_data(_websocket)
    use.echo_print(False, '::profile selected and updated', profile_data)


async def get_selected_profile() -> dict[dict]:
    data = await web_socket.recv()
    selected_profile = DataWeaver(byte_data=data)
    return selected_profile.content


async def configure_further_profile_data(_websocket):
    raw_profile_data = await web_socket.recv()
    profiles_data = DataWeaver(byte_data=raw_profile_data)
    for profile_name, profile_settings in profiles_data.content.items():
        profile_object = use.get_profile_from_username(profile_name)
        if profile_object is None:
            ProfileManager.add_profile(profile_name, profile_settings)
            continue
        for header, content in profile_settings.items():
            profile_object.edit_profile(header, content)


# -------------- ----------------- ----------------------- ------------------- -------------------- ---------------- -----------------

def end():
    global SafeEnd, web_socket
    SafeEnd.set()
    # web_socket.close() if web_socket else None
    asyncio.get_event_loop().stop() if asyncio.get_event_loop().is_running() else asyncio.get_event_loop().close()
    loop = asyncio.get_running_loop()
    loop.stop()
    loop.close()
    use.echo_print(True, "::Handle_signals Ended")
