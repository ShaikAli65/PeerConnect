from src.avails import DataWeaver, use
from src.core.transfers._headers import HEADERS
from src.core.webpage_handlers.pagehandle import dispatch_data
from src.managers import (
    ProfileManager,
    all_profiles,
    get_profile_from_profile_file_name,
    set_current_profile,
)


async def align_profiles(signal_data: DataWeaver):
    further_data = await send_profiles()
    await configure_further_profile_data(further_data)


def send_profiles():
    userdata = DataWeaver(header=HEADERS.HANDLE_PEER_LIST, content=all_profiles())
    use.echo_print("::profiles sent")
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
        ProfileManager.PROFILE_LIST = [
            profile
            for profile in ProfileManager.PROFILE_LIST
            if profile.username not in removed_profiles
        ]
        use.echo_print("deleted profiles :", removed_profiles)

    for profile_name, profile_settings in profiles_data.items():
        profile_object = get_profile_from_profile_file_name(profile_name)
        if profile_object is None:
            ProfileManager.add_profile(profile_name, profile_settings)
            use.echo_print("added profile :", profile_name, profile_settings)
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
    use.echo_print("::profile selected and updated", selected_profile)
