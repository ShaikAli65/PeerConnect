from src.core import *
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.managers.profile_manager import ProfileManager, set_selected_profile, all_profiles


async def align_profiles(_websocket):

    await send_profiles(_websocket)

    await configure_further_profile_data(_websocket)

    selected_profile = await get_selected_profile(_websocket)

    selected_profile_object: ProfileManager = get_profile_from_username(selected_profile)
    set_selected_profile(selected_profile_object)
    use.echo_print('::profile selected and updated', selected_profile_object)

    const.HOLD_PROFILE_SETUP.set()


async def send_profiles(_websocket):
    userdata = DataWeaver(header="this is a profiles list",
                          content=all_profiles())
    await _websocket.send(userdata.dump())
    use.echo_print('::profiles sent')


async def get_selected_profile(_websocket) -> str:
    data = await _websocket.recv()
    selected_profile = DataWeaver(byte_data=data)
    if selected_profile.header == "selected profile":
        return selected_profile.content


async def configure_further_profile_data(_websocket):

    raw_profile_data = await _websocket.recv()

    profiles_data = DataWeaver(byte_data=raw_profile_data)
    if not profiles_data.header == "new profile list":
        return profiles_data

    profiles_data = profiles_data.content

    if removed_profiles := set(all_profiles().keys()) - set(profiles_data):
        [ProfileManager.delete_profile(x) for x in removed_profiles]
        const.PROFILE_LIST = [profile for profile in const.PROFILE_LIST if profile.username not in removed_profiles]
        use.echo_print("deleted profiles :", removed_profiles)

    for profile_name, profile_settings in profiles_data.items():
        profile_object: ProfileManager = get_profile_from_username(profile_name)

        if profile_object is None:
            ProfileManager.add_profile(profile_name, profile_settings)
            continue

        for header, content in profile_settings.items():
            profile_object.edit_profile(header, content)


def get_profile_from_username(username: str) -> Union[ProfileManager, None]:
    """
    Retrieves profile object from list given username
    :param username:
    """
    '''
     for profile in const.PROFILE_LIST:
        if profile.username == username:
            return profile
     return None
    '''
    return next((profile for profile in const.PROFILE_LIST if profile.username == username), None)
