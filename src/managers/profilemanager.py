import asyncio
import configparser
import logging
import os
import time
from configparser import ConfigParser
from pathlib import Path
from typing import Optional, Union

from src.avails import const
from src.net import IPAddress

_logger = logging.getLogger(__name__)


async def write_config(config_parser, file_path):
    def _helper():
        with open(file_path, "w") as file:
            config_parser.write(file)

    # return _helper()
    return await asyncio.to_thread(_helper)


class ProfileManager:
    """
    Used to contain a profile instance of profiles
    it is recommended to discard this class's object if an error is raised somewhere in using
    as it can lead to unexpected behaviour.

    Attributes:
        username: username of the user
        id: id of the user
        interface: IPAddress[ip, scope_id, if_name, friendly_name]
        file_name: str  # profile path on disk
        transfers_agreed: dict[peer_id, agreed_or_not: bool]
    """

    main_config: ConfigParser = None
    PROFILE_LIST = []
    __slots__ = "profile_file_path", "_config_parser", "profile_data"

    def __init__(self, profiles_file, *, profile_data=None):
        self.profile_file_path = Path(const.PATH_PROFILES, profiles_file)
        self._config_parser = configparser.ConfigParser(allow_no_value=True)
        if profile_data:
            self.profile_data: dict[str, dict] = profile_data
            self._config_parser.update(profile_data)

    async def get_profile_data(self) -> dict:
        """
        Performs a structural pattern matching
        :raises ValueError: if required keys were not found
        :return profiles_data: if all required keys were found
        """

        profile_data = await self.__load_profile_data()
        self._match_pattern(profile_data)
        return profile_data

    def _match_pattern(self, profile_data):
        match profile_data:
            case {
                "USER": {
                    "name": _,
                    "id": _,
                },
                "INTERFACE": _
            }:
                return profile_data
            case _:
                raise LookupError(
                    f"something wrong in profile data\n:\tprofile at {self.profile_file_path}\ndata:"
                )

    async def __load_profile_data(self) -> dict:
        try:
            config = configparser.ConfigParser()
            await asyncio.to_thread(config.read, self.profile_file_path, encoding=None)
            return {
                section: dict(config.items(section)) for section in config.sections()
            }
        except FileNotFoundError:
            return {}

    async def edit_profile(self, config_header, new_settings: dict):
        """
            Accepts a dictionary of new settings and updates the profile with the new settings
            mapped to respective config_header
        """

        prev_username = self.username
        self.profile_data.setdefault(config_header, {}).update(new_settings)
        if not prev_username == self.username:
            new_profile_path = Path(
                const.PATH_PROFILES, self.__uniquify(self.username) + ".ini"
            )
            os.rename(self.profile_file_path, new_profile_path)
            await self.__remove_profile_from_main_config(self.profile_file_path.name)
            await self.__write_profile_to_main_config(new_profile_path.name)
            self.profile_file_path = new_profile_path

        await self.write_profile()

    async def set_profile_data_from_file(self):
        self.profile_data = await self.get_profile_data()

    async def write_interface(self, interface: IPAddress):
        return await self.edit_profile("INTERFACE", getattr(interface, '_asdict')())

    async def write_profile(self):
        self._config_parser.update(self.profile_data)
        await write_config(self._config_parser, self.profile_file_path)

    async def add_transfers_agreed(self, peer_id, agreed):
        self.profile_data.setdefault("TRANSFERS AGREED", {}).update({peer_id: agreed})
        await self.write_profile()

    @classmethod
    async def add_profile(cls, profile_name, settings: dict):
        """
         Adds profile into application with settings provided as a dictionary mapped to respective headers
        :return: ProfileManager
        """
        profile = cls(cls.__uniquify(profile_name) + ".ini", profile_data=settings)
        await profile.write_profile()
        await cls.__write_profile_to_main_config(profile.file_name)
        cls.PROFILE_LIST.append(profile)
        return profile

    @classmethod
    async def __write_profile_to_main_config(cls, file_name):
        cls.main_config.set("USER_PROFILES", file_name)
        # await write_config(cls._main_config, const.PATH_CONFIG_FILE)

        # these writes get updated when application is finalizing

    @classmethod
    async def __remove_profile_from_main_config(cls, profile_key):
        cls.main_config.remove_option("USER_PROFILES", profile_key)
        # await write_config(cls._main_config, const.PATH_CONFIG_FILE)

        # these writes get updated when application is finalizing

    @classmethod
    async def _clear_selected_profile(cls):
        if cls.main_config.has_section("SELECTED_PROFILE"):
            cls.main_config.remove_section("SELECTED_PROFILE")
        cls.main_config.add_section("SELECTED_PROFILE")

    @classmethod
    async def write_selected_profile(cls, profile):

        if cls.main_config.has_section("SELECTED_PROFILE"):
            cls.main_config.remove_section("SELECTED_PROFILE")

        cls.main_config.add_section("SELECTED_PROFILE")
        cls.main_config.set("SELECTED_PROFILE", profile.file_name)
        # await write_config(cls._main_config, const.PATH_CONFIG_FILE)

    @classmethod
    async def delete_profile(cls, profile_file_name):
        profile_path = Path(
            const.PATH_PROFILES, profile_file_name
        )
        if profile_path.exists():
            try:
                profile_path.unlink(True)
            except os.error as e:
                _logger.error(f"deletion error for profile {profile_file_name} exp:{e}")

        await cls.__remove_profile_from_main_config(profile_path.name)

        if profile_file_name == cls.prev_selected_profile_file_name():
            await cls._clear_selected_profile()

    @classmethod
    def prev_selected_profile_file_name(cls):
        """profile that user selected in the previous session"""
        return next(iter(cls.main_config["SELECTED_PROFILE"]), None)

    @property
    def username(self):
        return self.profile_data["USER"]["name"]

    @property
    def id(self) -> int:
        return self.profile_data["USER"]["id"]

    @property
    def interface(self):
        interface = self.profile_data["INTERFACE"]
        try:
            ip = interface["ip"]
            scope_id = int(interface["scope_id"])
            if_name = interface["if_name"]
            friendly_name = interface["friendly_name"]
        except KeyError:
            return None  # if any of these fail, it means not configured properly

        return IPAddress(ip, scope_id, if_name, friendly_name)

    @property
    def file_name(self):
        return self.profile_file_path.name

    @property
    def transfers_agreed(self):
        return self.profile_data.get("TRANSFERS AGREED", {})

    @staticmethod
    def __uniquify(username):
        return f"{username}{int(time.time() * 10)}"

    def __eq__(self, other):
        if isinstance(other, dict):
            return (
                    self.id == other["USER"]["id"]
                    and self.username == other["USER"]["name"]
            )
        if isinstance(other, ProfileManager):
            return self.id == other.id and self.username == other.username
        return self is other

    def __str__(self):
        return (
            f"<ProfileManager(\n"
            f"\tusername={self.username},\n"
            f"\tfile_name={self.file_name},\n"
            f"\tinterface={self.interface}\n"
            f"\ttransfers-agreed={len(self.transfers_agreed)} peers\n"
            f")"
            f"{' selected ' if self.prev_selected_profile_file_name() == self.file_name else ''}"
            ">"
        )

    def __repr__(self):
        return f"<Profile name={self.username} file_path={self.profile_file_path}>"


def all_profiles():
    """
    give all profiles available as {username:settings} given by their ProfileManager object

    Notes:
        make sure that you definitely call :func:`load_profiles_to_program()` in prior,
    Returns:
         dict[str, ProfileManager]
    """
    profiles = {
        profile.file_name: profile.profile_data.copy()
        for profile in ProfileManager.PROFILE_LIST
    }
    prev = ProfileManager.prev_selected_profile_file_name()

    if prev in profiles:
        profiles[prev].update({
            'selected': True,
        })

    return profiles


async def load_profiles_to_program(main_config):
    assert os.path.exists(const.PATH_PROFILES), "profiles path not found"
    ProfileManager.main_config = main_config
    for profile_id in main_config["USER_PROFILES"]:
        try:
            # Note: only places where profile objects are created:
            # 1. ProfileManager.add_profile
            # 2. here

            profile = ProfileManager(profile_id)
            await profile.set_profile_data_from_file()
            ProfileManager.PROFILE_LIST.append(profile)
        except LookupError:
            await ProfileManager.delete_profile(profile_id)

    _logger.debug(f"loaded profiles: {'\n'.join(str(x) for x in ProfileManager.PROFILE_LIST)} \n")
    return ProfileManager.PROFILE_LIST


async def refresh_profile_list():
    ProfileManager.PROFILE_LIST.clear()
    _logger.debug(f"reloading profiles")
    await load_profiles_to_program(ProfileManager.main_config)


def get_profile_from_profile_file_name(
        profile_file_name,
) -> Union[ProfileManager, None]:
    """
    Retrieves profile object from list given username
    :param profile_file_name:
    """
    return next(
        (
            profile
            for profile in ProfileManager.PROFILE_LIST
            if profile.file_name == profile_file_name
        ),
        None,
    )


_current_profile: Optional[ProfileManager] = None


async def set_current_profile(profile):
    global _current_profile
    _current_profile = profile
    await ProfileManager.write_selected_profile(profile)


def get_current_profile() -> ProfileManager:
    global _current_profile
    return _current_profile
