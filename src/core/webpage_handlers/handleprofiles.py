from src.avails import DataWeaver, use
from src.core.transfers import HEADERS
from src.core.webpage_handlers.pagehandle import dispatch_data
from src.managers import (
    ProfileManager,
    all_profiles,
    get_profile_from_profile_file_name,
    refresh_profile_list, set_current_profile,
)


async def align_profiles(signal_data: DataWeaver):
    further_data = await send_profiles()
    await configure_further_profile_data(further_data)
    refresh_profile_list()


def send_profiles():
    userdata = DataWeaver(header=HEADERS.HANDLE_PEER_LIST, content=all_profiles())
    use.echo_print("::[HANDLE PROFILES] profiles sent")
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
        use.echo_print("deleted profiles :", removed_profiles)

    for may_be_profile_name, profile_settings in profiles_data.items():
        profile_object = get_profile_from_profile_file_name(may_be_profile_name)
        if profile_object is None:
            profile_settings['USER']['id'] = int(profile_settings['USER']['id'])  # = new_remote_peer_id()
            profile_name = profile_settings['USER']['name']

            # new profile does not have any id associated with it
            try:
                ProfileManager.add_profile(profile_name, profile_settings)
            except Exception as e:
                print("-" * 80, e)
            use.echo_print("[HANDLE PROFILE] added profile :", may_be_profile_name, profile_settings)
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
