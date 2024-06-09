from src.core import *
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.managers.profile_manager import ProfileManager, all_profiles, get_profile_from_profile_file_name
from src.configurations.configure_app import set_selected_profile


async def align_profiles(_websocket):
    if const.HOLD_PROFILE_SETUP.is_set():
        return
    await send_profiles(_websocket)

    await configure_further_profile_data(_websocket)

    selected_profile = await get_selected_profile(_websocket)
    set_selected_profile(selected_profile)
    use.echo_print('::profile selected and updated', selected_profile)

    const.HOLD_PROFILE_SETUP.set()


async def send_profiles(_websocket):
    userdata = DataWeaver(header="this is a profiles list",
                          content=all_profiles())

    await _websocket.send(userdata.dump())
    use.echo_print('::profiles sent')


async def get_selected_profile(_websocket):
    data = await _websocket.recv()
    # print("selected",data)  # debug
    selected_profile = DataWeaver(byte_data=data)
    if selected_profile.header == "selected profile":
        for profile in const.PROFILE_LIST:
            if profile == selected_profile.content:
                return profile


async def configure_further_profile_data(_websocket):

    raw_profile_data = await _websocket.recv()
    # print(raw_profile_data)  # debug
    profiles_data = DataWeaver(byte_data=raw_profile_data)
    if not profiles_data.header == "new profile list":
        return profiles_data

    profiles_data = profiles_data.content
    """
    profiles_data structure
    {
         # cause these are unique
        file_name : {
            'USER' : {
                'name' : *,
            },
            'SERVER' : {
                'ip' : *,
                'port' : *,
                'id' : *,
            },
        },
        ...
    }
    """
    if removed_profiles := set(all_profiles()) - set(profiles_data):
        for profile_file_name in removed_profiles:
            ProfileManager.delete_profile(profile_file_name)

        const.PROFILE_LIST = [profile for profile in const.PROFILE_LIST if profile.username not in removed_profiles]
        use.echo_print("deleted profiles :", removed_profiles)
    for profile_name, profile_settings in profiles_data.items():
        profile_object = get_profile_from_profile_file_name(profile_name)
        if profile_object is None:
            ProfileManager.add_profile(profile_name, profile_settings)
            continue

        for header, content in profile_settings.items():
            profile_object.edit_profile(header, content)
