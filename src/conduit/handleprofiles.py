import asyncio

from src.avails import DataWeaver
from src.conduit import logger, webpage
from src.conduit.pagehandle import PROFILE_WAIT
from src.configurations import interfaces
from src.configurations.interfaces import get_interfaces
from src.managers import (
    ProfileManager,
    all_profiles,
    get_profile_from_profile_file_name,
    refresh_profile_list, set_current_profile,
)

_alignment_done = asyncio.Event()


async def align_profiles(_: DataWeaver):
    interfaces.reset()
    _alignment_done.clear()
    logger.info("[PROFILES] sending profiles")
    updated_profiles = await webpage.send_profiles_and_get_updated_profiles(
        all_profiles(), get_interfaces()
    )
    await configure_further_profile_data(updated_profiles)
    _alignment_done.set()


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
            profile_settings['USER']['id'] = int(profile_settings['USER']['id'])  # = new_remote_peer_id()
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


async def set_selected_profile(page_data: DataWeaver):
    await _alignment_done.wait()

    assert PROFILE_WAIT is not None, "PROFILE WAIT IS NONE"

    if PROFILE_WAIT.done():
        logger.warning(f"current profile is already set, ignoring choice {page_data}")
        return
    
    await refresh_profile_list()
    for profile in ProfileManager.PROFILE_LIST:
        profile: ProfileManager
        if profile == page_data.content:
            assert profile.interface is not None, "interface not configured properly can't select this profile"
            assert bool(profile.file_name) is True, "file name not configured properly can't select this profile"
            assert bool(profile.id) is True, "id not configured properly can't select this profile"

            await set_current_profile(profile)
            logger.info(f"profile selected and updated {profile=}")
            PROFILE_WAIT.set_result(profile)
            return

    logger.critical("selected profile not found in current list")
