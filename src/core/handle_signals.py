import websockets

from src.configurations.boot_up import launch_web_page
from src.core import *
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.managers.profile_manager import all_profiles, set_selected_profile, ProfileManager  # , load_profiles_to_program

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
    launch_web_page()
    asyncio.set_event_loop(asyncio.new_event_loop())
    start_server = websockets.serve(handler, "localhost", const.PORT_PAGE_SIGNALS)
    # start_server = websockets.serve(handler, "172.16.197.166", const.PORT_PAGE_SIGNALS)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()


# ----------------------------------------------------profile handlers---------------------------------------------------------------


async def align_profiles(_websocket):

    await send_profiles(_websocket)

    await configure_further_profile_data(_websocket)

    selected_profile = await get_selected_profile()

    selected_profile_object: ProfileManager = get_profile_from_username(selected_profile)
    set_selected_profile(selected_profile_object)
    use.echo_print(False, '::profile selected and updated', selected_profile_object)

    const.HOLD_PROFILE_SETUP.set()


async def send_profiles(_websocket):
    userdata = DataWeaver(header="this is a profiles list",
                          content=all_profiles())
    await web_socket.send(userdata.dump())
    use.echo_print(False, '::profiles sent')


async def get_selected_profile() -> str:
    data = await web_socket.recv()
    selected_profile = DataWeaver(byte_data=data)
    if selected_profile.header == "selected profile":
        return selected_profile.content


# @NotInUse
async def configure_further_profile_data(_websocket):
    raw_profile_data = await web_socket.recv()
    profiles_data = DataWeaver(byte_data=raw_profile_data)
    if not profiles_data.header == "new profile list":
        return profiles_data
    # use.echo_print(False, "new profile list :",profiles_data.content)
    profiles_data = profiles_data.content

    removed_profiles = set(all_profiles().keys()) - set(profiles_data)
    [ProfileManager.delete_profile(x) for x in removed_profiles]
    print("deleted profiles :", removed_profiles)

    for profile_name, profile_settings in profiles_data.items():
        profile_object: ProfileManager = get_profile_from_username(profile_name)

        if profile_object is None:
            ProfileManager.add_profile(profile_name, profile_settings)
            continue

        for header, content in profile_settings.items():
            profile_object.edit_profile(header, content)


def get_profile_from_username(username: str) -> Union[ProfileManager,None]:
    """
    Retrieves profile object from list given username
    :param username:
    """
    for profile in const.PROFILE_LIST:
        if profile.username == username:
            return profile
    return None

# -------------- ----------------- ----------------------- ------------------- -------------------- ---------------- -----------------


def end():
    global SafeEnd, web_socket
    SafeEnd.set()
    web_socket.close() if web_socket else None
    asyncio.get_event_loop().stop() if asyncio.get_event_loop().is_running() else asyncio.get_event_loop().close()
    loop = asyncio.get_running_loop()
    loop.stop()
    # loop.close()
    const.END_OR_NOT = True
    const.HOLD_PROFILE_SETUP.set()
    use.echo_print(True, "::Handle_signals Ended")
