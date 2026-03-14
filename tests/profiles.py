import asyncio
import logging
import os

import _path  # noqa
from src.configurations.configure import load_configs, set_paths
from src.configurations.interfaces import get_interfaces, get_ip_with_ip
from src.core.app import App
from src.managers import logmanager, profilemanager

_logger = logging.getLogger(__name__)

app = App


def _get_selected(profiles):
    for profile_file_name, profile in profiles.items():
        if "selected" in profile:
            return profile_file_name, profile

    return None, None


async def test_check_loading():
    app.current_config = await load_configs(app.exit_stack)
    _logger.info("[TEST PASSED] found current_config healthy")
    profiles_len = len(app.current_config["USER_PROFILES"])
    await profilemanager.load_profiles_to_program(app.current_config)
    profiles = profilemanager.all_profiles()
    assert len(profiles) > 0, "expected some profiles"
    _logger.info("[TEST PASSED] found some profiles")
    assert len(profiles) == profiles_len, "not all profiles loaded"
    _logger.info("[TEST PASSED] all profiles loaded")


async def test_check_selected_profile():
    profiles = profilemanager.all_profiles()
    prev_selected = profilemanager.ProfileManager.prev_selected_profile_file_name()
    selected_prof = next(iter(app.current_config["USER_PROFILES"]))
    app.current_config.set("SELECTED_PROFILE", selected_prof)
    await profilemanager.refresh_profile_list()

    assert _get_selected(profiles)[0] == selected_prof, "expected selected profile"
    _logger.info("[TEST PASSED] selected profile found")
    app.current_config.remove_option("SELECTED_PROFILE", prev_selected)

    await profilemanager.refresh_profile_list()
    profiles = profilemanager.all_profiles()
    assert _get_selected(profiles)[0] is None, "not expected selected profile"
    app.current_config.set("SELECTED_PROFILE", prev_selected)
    _logger.info("[TEST PASSED] selected profile not found")


async def test_create_profile():
    profile = await profilemanager.ProfileManager.add_profile(
        'testing-profile', {
            "USER": {
                "name": "test-profile",
                "id": 496307574572071141284940744555912231242715614053,
            },
            "INTERFACE": {
                "ip": "192.168.137.25",
                "scope_id": "-1",
                "if_name": "b'{E7124DFD-A6AC-4DDD-A66C-B188C5F7BC6A}'",
                "friendly_name": "Wi-Fi",
            }
        }
    )
    profile_names = list(app.current_config["USER_PROFILES"])

    assert profile.file_name in profile_names, "expected test profile in basic_config under USER_PROFILES section"
    _logger.info("[TEST PASSED] found added profile inside basic config")

    await profilemanager.refresh_profile_list()
    profiles = profilemanager.all_profiles()

    assert profile.file_name in profiles.keys(), "expected test profile in dict returned by all_profiles"
    _logger.info("[TEST PASSED] found added profile inside list returned by all_profiles")

    assert os.path.exists(profile.profile_file_path), "not found added profile file"
    _logger.info("[TEST PASSED] found added profile in file system")

    return profile


async def test_update_profile(one_profile):
    prev_name = one_profile.username

    await one_profile.edit_profile("USER", {"name": "new test name"})
    assert one_profile.username == "new test name", "editing profile failed"
    _logger.info("[TEST PASSED] name updated successfully")
    await one_profile.edit_profile("USER", {"name": prev_name})

    interface = next(iter(get_interfaces()))
    await one_profile.write_interface(interface)
    assert interface == get_ip_with_ip(one_profile.interface.ip), "failed to update interface"
    _logger.info("[TEST PASSED] interface updated successfully")


async def test_delete_profile(profile: profilemanager.ProfileManager):
    await profilemanager.ProfileManager.delete_profile(profile.file_name)
    await profilemanager.refresh_profile_list()
    for prof in profilemanager.ProfileManager.PROFILE_LIST:
        assert not profile == prof, "expected profile to be deleted"

    _logger.info("[TEST PASSED] profile deleted successfully")


async def test_profiles():
    _logger.info("")
    await test_check_loading()
    await test_check_selected_profile()
    profile = await test_create_profile()
    await test_update_profile(profile)
    await test_delete_profile(profile)

    _logger.info("11/11 tests passed for profiles")


async def main():
    async with app.exit_stack:
        set_paths()
        await logmanager.initiate(app)
        await test_profiles()


if __name__ == "__main__":
    asyncio.run(main())
