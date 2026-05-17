import asyncio
import configparser

import pytest

from src.avails import const
from src.managers import profilemanager
from src.managers.profilemanager import (
    ProfileManager,
    all_profiles,
    get_current_profile,
    get_profile_from_profile_file_name,
    load_profiles_to_program,
    refresh_profile_list,
    set_current_profile,
)
from src.net import IPAddress


def profile_settings(name="alice", profile_id="peer-1", interface=None):
    return {
        "USER": {
            "name": name,
            "id": profile_id,
        },
        "INTERFACE": interface
        or {
            "ip": "127.0.0.1",
            "scope_id": "3",
            "if_name": "lo",
            "friendly_name": "Loopback",
        },
    }


@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    main_config = configparser.ConfigParser(allow_no_value=True)
    main_config.add_section("USER_PROFILES")
    main_config.add_section("SELECTED_PROFILE")

    monkeypatch.setattr(const, "PATH_PROFILES", profiles_dir)
    monkeypatch.setattr(profilemanager, "_current_profile", None)

    async def to_thread_inline(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", to_thread_inline)
    ProfileManager.PROFILE_LIST.clear()
    ProfileManager.main_config = main_config

    yield profiles_dir, main_config

    ProfileManager.PROFILE_LIST.clear()
    ProfileManager.main_config = None
    profilemanager._current_profile = None


def write_profile_file(path, settings):
    parser = configparser.ConfigParser()
    parser.read_dict(settings)
    with path.open("w") as file:
        parser.write(file)


@pytest.mark.asyncio
async def test_get_profile_data_loads_valid_profile(profile_env):
    profiles_dir, _ = profile_env
    write_profile_file(profiles_dir / "alice.ini", profile_settings())
    manager = ProfileManager("alice.ini")

    data = await manager.get_profile_data()

    assert data["USER"] == {"name": "alice", "id": "peer-1"}
    assert data["INTERFACE"]["ip"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_get_profile_data_rejects_missing_required_sections(profile_env):
    profiles_dir, _ = profile_env
    write_profile_file(profiles_dir / "broken.ini", {"USER": {"name": "alice"}})
    manager = ProfileManager("broken.ini")

    with pytest.raises(LookupError):
        await manager.get_profile_data()


@pytest.mark.asyncio
async def test_add_profile_writes_file_registers_main_config_and_profile_list(
    profile_env,
    monkeypatch,
):
    profiles_dir, main_config = profile_env
    monkeypatch.setattr(profilemanager.time, "time", lambda: 123.4)

    manager = await ProfileManager.add_profile("alice", profile_settings())

    assert manager.file_name == "alice1234.ini"
    assert (profiles_dir / "alice1234.ini").exists()
    assert "alice1234.ini" in main_config["USER_PROFILES"]
    assert ProfileManager.PROFILE_LIST == [manager]

    loaded = configparser.ConfigParser()
    loaded.read(profiles_dir / "alice1234.ini")
    assert loaded["USER"]["name"] == "alice"
    assert loaded["INTERFACE"]["if_name"] == "lo"


@pytest.mark.asyncio
async def test_edit_profile_updates_file_without_renaming_when_username_unchanged(profile_env):
    profiles_dir, main_config = profile_env
    manager = ProfileManager("alice.ini", profile_data=profile_settings())
    main_config.set("USER_PROFILES", "alice.ini")
    await manager.write_profile()

    await manager.edit_profile("INTERFACE", {"friendly_name": "Localhost"})

    assert manager.file_name == "alice.ini"
    assert (profiles_dir / "alice.ini").exists()
    assert "alice.ini" in main_config["USER_PROFILES"]

    loaded = configparser.ConfigParser()
    loaded.read(profiles_dir / "alice.ini")
    assert loaded["INTERFACE"]["friendly_name"] == "Localhost"


@pytest.mark.asyncio
async def test_edit_profile_renames_file_and_updates_main_config_on_username_change(
    profile_env,
    monkeypatch,
):
    profiles_dir, main_config = profile_env
    manager = ProfileManager("alice.ini", profile_data=profile_settings())
    main_config.set("USER_PROFILES", "alice.ini")
    await manager.write_profile()
    monkeypatch.setattr(profilemanager.time, "time", lambda: 200.0)

    await manager.edit_profile("USER", {"name": "bob"})

    assert manager.file_name == "bob2000.ini"
    assert not (profiles_dir / "alice.ini").exists()
    assert (profiles_dir / "bob2000.ini").exists()
    assert "alice.ini" not in main_config["USER_PROFILES"]
    assert "bob2000.ini" in main_config["USER_PROFILES"]

    loaded = configparser.ConfigParser()
    loaded.read(profiles_dir / "bob2000.ini")
    assert loaded["USER"]["name"] == "bob"


def test_interface_returns_ipaddress_and_missing_interface_fields_return_none(profile_env):
    manager = ProfileManager("alice.ini", profile_data=profile_settings())

    assert manager.interface == IPAddress("127.0.0.1", 3, "lo", "Loopback")

    manager.profile_data["INTERFACE"].pop("friendly_name")
    assert manager.interface is None


@pytest.mark.asyncio
async def test_write_interface_persists_ipaddress_fields(profile_env):
    profiles_dir, _ = profile_env
    manager = ProfileManager("alice.ini", profile_data=profile_settings())
    await manager.write_profile()

    await manager.write_interface(IPAddress("192.168.1.5", 7, "eth0", "Ethernet"))

    assert manager.interface == IPAddress("192.168.1.5", 7, "eth0", "Ethernet")
    loaded = configparser.ConfigParser()
    loaded.read(profiles_dir / "alice.ini")
    assert loaded["INTERFACE"]["ip"] == "192.168.1.5"
    assert loaded["INTERFACE"]["scope_id"] == "7"
    assert loaded["INTERFACE"]["if_name"] == "eth0"


@pytest.mark.asyncio
async def test_add_transfers_agreed_creates_section_and_persists_decision(profile_env):
    profiles_dir, _ = profile_env
    manager = ProfileManager("alice.ini", profile_data=profile_settings())
    await manager.write_profile()

    await manager.add_transfers_agreed("peer-2", True)

    assert manager.transfers_agreed == {"peer-2": True}
    loaded = configparser.ConfigParser()
    loaded.read(profiles_dir / "alice.ini")
    assert loaded["TRANSFERS AGREED"]["peer-2"] == "True"


@pytest.mark.asyncio
async def test_write_selected_and_set_current_profile_update_global_selection(profile_env):
    _, main_config = profile_env
    manager = ProfileManager("alice.ini", profile_data=profile_settings())

    await ProfileManager.write_selected_profile(manager)
    assert ProfileManager.prev_selected_profile_file_name() == "alice.ini"

    other = ProfileManager("bob.ini", profile_data=profile_settings("bob", "peer-2"))
    await set_current_profile(other)

    assert get_current_profile() is other
    assert ProfileManager.prev_selected_profile_file_name() == "bob.ini"
    assert list(main_config["SELECTED_PROFILE"]) == ["bob.ini"]


@pytest.mark.asyncio
async def test_delete_profile_removes_file_main_config_entry_and_selected_profile(profile_env):
    profiles_dir, main_config = profile_env
    path = profiles_dir / "alice.ini"
    path.write_text("[USER]\nname = alice\nid = peer-1\n[INTERFACE]\n")
    main_config.set("USER_PROFILES", "alice.ini")
    main_config.set("SELECTED_PROFILE", "alice.ini")

    await ProfileManager.delete_profile("alice.ini")

    assert not path.exists()
    assert "alice.ini" not in main_config["USER_PROFILES"]
    assert list(main_config["SELECTED_PROFILE"]) == []


@pytest.mark.asyncio
async def test_load_profiles_to_program_loads_valid_profiles_and_removes_invalid_entries(
    profile_env,
):
    profiles_dir, main_config = profile_env
    write_profile_file(profiles_dir / "valid.ini", profile_settings())
    write_profile_file(profiles_dir / "invalid.ini", {"USER": {"name": "broken"}})
    main_config.set("USER_PROFILES", "valid.ini")
    main_config.set("USER_PROFILES", "invalid.ini")

    profiles = await load_profiles_to_program(main_config)

    assert [profile.file_name for profile in profiles] == ["valid.ini"]
    assert "valid.ini" in main_config["USER_PROFILES"]
    assert "invalid.ini" not in main_config["USER_PROFILES"]


@pytest.mark.asyncio
async def test_refresh_profile_list_reloads_from_main_config(profile_env):
    profiles_dir, main_config = profile_env
    write_profile_file(profiles_dir / "alice.ini", profile_settings())
    main_config.set("USER_PROFILES", "alice.ini")
    ProfileManager.PROFILE_LIST.append(
        ProfileManager("stale.ini", profile_data=profile_settings("stale"))
    )

    await refresh_profile_list()

    assert [profile.file_name for profile in ProfileManager.PROFILE_LIST] == ["alice.ini"]


def test_all_profiles_marks_selected_and_lookup_finds_by_file_name(profile_env):
    _, main_config = profile_env
    alice = ProfileManager("alice.ini", profile_data=profile_settings())
    bob = ProfileManager("bob.ini", profile_data=profile_settings("bob", "peer-2"))
    ProfileManager.PROFILE_LIST.extend([alice, bob])
    main_config.set("SELECTED_PROFILE", "bob.ini")

    profiles = all_profiles()

    assert get_profile_from_profile_file_name("alice.ini") is alice
    assert get_profile_from_profile_file_name("missing.ini") is None
    assert "selected" not in profiles["alice.ini"]
    assert profiles["bob.ini"]["selected"] is True


def test_profile_equality_uses_user_id_and_name(profile_env):
    manager = ProfileManager("alice.ini", profile_data=profile_settings())
    same = ProfileManager("copy.ini", profile_data=profile_settings())
    different = ProfileManager("bob.ini", profile_data=profile_settings("bob"))

    assert manager == same
    assert manager == profile_settings()
    assert manager != different
    assert manager != object()
