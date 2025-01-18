from src.avails import DataWeaver
from src.managers import (
    ProfileManager,
    all_profiles,
    get_profile_from_profile_file_name,
    refresh_profile_list, set_current_profile,
)
from src.webpage_handlers import logger
from src.webpage_handlers.headers import HANDLE
from src.webpage_handlers.pagehandle import PROFILE_WAIT, dispatch_data


async def align_profiles(signal_data: DataWeaver):
    further_data = await send_profiles()
    await configure_further_profile_data(further_data)
    refresh_profile_list()
    PROFILE_WAIT.set()


def send_profiles():
    userdata = DataWeaver(header=HANDLE.PEER_LIST, content=all_profiles())
    logger.info("::[PROFILES] sending profiles")
    return dispatch_data(userdata, expect_reply=True)


async def configure_further_profile_data(profiles_data):
    profiles_data = profiles_data.content
    """
    profiles_data structure
    {
        file_name : {
            'USER' : {
                'name' : *,
                'id' : *,
            },
            'SERVER' : {
                'ip' : *,
                'port' : *,
            },
        },
        ...
    }
    """
    if removed_profiles := set(all_profiles()) - set(profiles_data):
        for profile_file_name in removed_profiles:
            ProfileManager.delete_profile(profile_file_name)
        logger.info(f"deleted profiles: {removed_profiles}")

    for may_be_profile_name, profile_settings in profiles_data.items():
        profile_object = get_profile_from_profile_file_name(may_be_profile_name)
        if profile_object is None:
            profile_settings['USER']['id'] = int(profile_settings['USER']['id'])  # = new_remote_peer_id()
            profile_name = profile_settings['USER']['name']

            # new profile does not have any id associated with it
            ProfileManager.add_profile(profile_name, profile_settings)
            logger.info(f"[HANDLE PROFILE] added profile :{may_be_profile_name}, {profile_settings}")
            continue

        for header, content in profile_settings.items():
            profile_object.edit_profile(header, content)


async def set_selected_profile(page_data: DataWeaver):
    selected_profile = page_data
    for profile in ProfileManager.PROFILE_LIST:
        if profile == selected_profile.content:
            selected_profile = profile
            break
    set_current_profile(selected_profile)
    logger.info(f"profile selected and updated {selected_profile=}")
