from src.conduit.bases import FrontEnd
from src.avails import use
from src.conduit import logger
from src.conduit.ui_events import ProfileDataExchange, ProfileDataExchangeReply
from src.configurations import interfaces
from src.managers import (
    ProfileManager,
    all_profiles,
    get_profile_from_profile_file_name,
    refresh_profile_list, set_current_profile,
)


async def align_profiles(frontend: FrontEnd):
    interfaces.reset()
    logger.info("sending profiles")
    profile_data = ProfileDataExchange(
        use.get_unique_id(str),
        profiles=all_profiles(),
        interfaces=[getattr(v, '_asdict')() for v in interfaces.get_interfaces()]
    )

    updated_profiles = await frontend.send_prompt_and_get_response(
        profile_data, ProfileDataExchangeReply
    )
    await configure_further_profile_data(updated_profiles.profiles)
    return updated_profiles.selected_profile


async def configure_further_profile_data(profiles_data):
    """

    profiles_data structure::

        {
            file_name : {
                'USER' : {
                    'name' : *,
                    'id' : *,
                },
                # 'SERVER' : {
                #     'ip' : *,
                #     'port' : *,
                # },
                "INTERFACE": {
                    ip = 127.234.2.93
                    scope_id = -1
                    if_name = b'{TEST}'
                    friendly_name = testing
                }
            },
            ...
        }

    Args:
        profiles_data(dict): ...
    """
    if removed_profiles := set(all_profiles()) - set(profiles_data):
        for profile_file_name in removed_profiles:
            await ProfileManager.delete_profile(profile_file_name)
        logger.info(f"deleted profiles: {removed_profiles}")

    for may_be_profile_name, profile_settings in profiles_data.items():
        profile_object = get_profile_from_profile_file_name(may_be_profile_name)
        if profile_object is None:
            profile_settings['USER']['id'] = int(profile_settings['USER']['id'])
            preferred_ip = interfaces.get_ip_with_ifname(profile_settings["INTERFACE"]["if_name"])
            profile_settings["INTERFACE"] = getattr(preferred_ip, '_asdict')()

            # new profile does not have any id associated with it
            profile_name = profile_settings['USER']['name']
            await ProfileManager.add_profile(profile_name, profile_settings)
            logger.info(f"[HANDLE PROFILE] added profile :{may_be_profile_name}, {profile_settings}")
            continue

        for header, content in profile_settings.items():
            preferred_ip = interfaces.get_ip_with_ifname(profile_settings["INTERFACE"]["if_name"])
            profile_settings["INTERFACE"] = getattr(preferred_ip, '_asdict')()
            await profile_object.edit_profile(header, content)


async def set_selected_profile(selected_profile):

    await refresh_profile_list()
    for profile in ProfileManager.PROFILE_LIST:
        profile: ProfileManager
        if profile == selected_profile.profile:
            assert profile.interface is not None, "interface not configured properly can't select this profile"
            assert bool(
                profile.file_name) is True, "file name not configured properly can't select this profile"
            assert bool(profile.id) is True, "id not configured properly can't select this profile"

            await set_current_profile(profile)
            logger.info(f"profile selected and updated {profile=}")
            return profile

    logger.critical("selected profile not found in current list")
    return None
