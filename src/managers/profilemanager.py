import asyncio
import configparser
import os
import time
from pathlib import Path
from typing import Optional, Union

from src.avails import const
from src.avails.connect import IPAddress


async def write_config(config_parser, file_path):
    def _helper():
        with open(file_path, "w") as file:
            config_parser.write(file)
    # return _helper()
    return await asyncio.to_thread(_helper)


class ProfileManager:
    """
    This class used to contain a profile instance of profiles
    it is recommended to discard this class's object if an error is raised somewhere in using
    as it can lead to unexpected behaviour
    """

    _main_config = configparser.ConfigParser(allow_no_value=True)
    PROFILE_LIST = []

    def __init__(self, profiles_file, *, profile_data=None):
        self.profile_file_path = Path(const.PATH_PROFILES, profiles_file)
        if profile_data:
            self.profile_data: dict[str, dict] = profile_data

    async def get_profile_data(self) -> dict:
        """
        Performs a structural pattern matching
        :raises ValueError: if required keys were not found
        :return profiles_data: if all required keys were found
        """

        profile_data = await self.__load_profile_data()
        self.match_pattern(profile_data)
        return profile_data

    def match_pattern(self, profile_data):
        match profile_data:
            case {
                "SERVER": {
                    "ip": _,
                    "port": _,
                },
                "USER": {
                    "name": _,
                    "id": _,
                },
                "INTERFACE": _
            }:
                return profile_data
            case _:
                self.__raise_error()

    async def __load_profile_data(self) -> dict:
        try:
            config = configparser.ConfigParser()
            # config.read(self.profile_file_path)
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
            await self.__remove_from_main_config(self.profile_file_path.name)
            await self.__write_to_main_config(new_profile_path.name)
            self.profile_file_path = new_profile_path
        await self._write_profile()

    async def set_profile_data_from_file(self):
        self.profile_data = await self.get_profile_data()

    async def write_interface(self, interface: IPAddress):
        return await self.edit_profile("INTERFACES", interface._asdict())

    async def _write_profile(self):
        config = configparser.ConfigParser()
        config.update(
            {profile: settings for profile, settings in self.profile_data.items()}
        )

        await write_config(config, self.profile_file_path)


    def __raise_error(self):
        raise LookupError(
            f"something wrong in profile data\n:\tprofile at {self.profile_file_path}\ndata:"
        )

    @classmethod
    async def add_profile(cls, profile_name, settings: dict):
        """
         Adds profile into application with settings provided as a dictionary mapped to respective headers
        :param profile_name:
        :param settings:
        :return:
        """
        profile_path = Path(const.PATH_PROFILES, cls.__uniquify(profile_name) + ".ini")
        config = configparser.ConfigParser()
        for section, setting in settings.items():
            config[section] = setting
        await write_config(config, profile_path)
        await cls.__write_to_main_config(profile_path.name)
        cls.PROFILE_LIST.append(p := cls(profile_path, profile_data=settings))
        # await p.set_profile_data_from_file()
        return p

    @classmethod
    async def __write_to_main_config(cls, file_name):
        cls._main_config.set("USER_PROFILES", file_name)
        await write_config(cls._main_config, const.PATH_CONFIG)

    @classmethod
    async def __remove_from_main_config(cls, profile_key):
        cls._main_config.remove_option("USER_PROFILES", profile_key)  # debug
        await write_config(cls._main_config, const.PATH_CONFIG)

    @classmethod
    async def _clear_selected_profile(cls):
        """writes default profile as the last selected one"""
        default = ProfileManager(Path(const.PATH_PROFILES, const.DEFAULT_PROFILE_NAME))
        await cls.write_selected_profile(default)

    @classmethod
    async def write_selected_profile(cls, profile):
        cls._main_config.remove_section("SELECTED_PROFILE")
        await write_config(cls._main_config, const.PATH_CONFIG)

        cls._main_config.add_section("SELECTED_PROFILE")
        cls._main_config.set("SELECTED_PROFILE", profile.file_name)
        await write_config(cls._main_config, const.PATH_CONFIG)

    @classmethod
    async def delete_profile(cls, profile_file_name):
        profile_path = Path(
            const.PATH_PROFILES, profile_file_name
        )
        if profile_path.is_file():
            try:
                profile_path.unlink(True)
            except os.error as e:
                # error_log(f"deletion error for profile {profile_file_name} exp:{e}")
                ...
        await cls.__remove_from_main_config(profile_path.name)

        if profile_file_name == cls.prev_selected_profile_file_name():
            await cls._clear_selected_profile()

    def __repr__(self):
        return f"<Profile name={self.username} file_path={self.profile_file_path}>"

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
            scope_id = interface["scope_id"]
            if_name = interface["if_name"]
            friendly_name = interface["friendly_name"]
        except KeyError:
            return None  # if any of these fail, it means not configured properly

        return IPAddress(ip, scope_id, if_name, friendly_name)

    @property
    def file_name(self):
        return self.profile_file_path.name

    @property
    def server_ip(self):
        return self.profile_data["SERVER"]["ip"]

    @staticmethod
    def __uniquify(username):
        return f"{username}{int(time.time() * 10)}"

    @classmethod
    def prev_selected_profile_file_name(cls):
        """profile that user selected in the previous session"""
        return next(iter(cls._main_config["SELECTED_PROFILE"]))

    def __eq__(self, other):
        if isinstance(other, dict):
            return (
                    self.id == other["USER"]["id"]
                    and self.username == other["USER"]["name"]
                    and self.server_ip == other["SERVER"]["ip"]
            )
        if isinstance(other, ProfileManager):
            return self.id == other.id and self.username == other.username
        return self is other

    def __str__(self):
        return (
            f"<ProfileManager(\n"
            f"\tserver_ip={self.server_ip},\n"
            f"\tusername={self.username},\n"
            f"\tfile_name={self.file_name},\n"
            f"\tinterface={self.interface}\n"
            f")>"
        )


def all_profiles():
    """
    give all profiles available as key{username} mapped to their settings given by their ProfileManager object
    make sure that you definitely call :func:`load_profiles_to_program()` in prior,
    :return dict[str, ProfileManager]:
    """
    profiles = {
        profile.file_name: profile.profile_data.copy()
        for profile in ProfileManager.PROFILE_LIST
    }
    prev = ProfileManager.prev_selected_profile_file_name()
    if prev not in profiles:
        prev = const.DEFAULT_PROFILE_NAME

    profiles[prev].update({
        'selected': True,
    })

    return profiles


async def load_profiles_to_program():
    if not os.path.exists(const.PATH_PROFILES):
        print("profiles path not found")
        exit(-1)

    main_config = configparser.ConfigParser(allow_no_value=True)
    await asyncio.to_thread(main_config.read, filenames=const.PATH_CONFIG, encoding=None)

    ProfileManager._main_config = main_config
    for profile_id in main_config["USER_PROFILES"]:
        try:
            # this is the only place where profile objects are created
            profile = ProfileManager(profile_id)
            await profile.set_profile_data_from_file()
            ProfileManager.PROFILE_LIST.append(profile)
        except LookupError:
            await ProfileManager.delete_profile(profile_id)

    if const.debug:
        print(f"loaded profiles: \n {"\n".join(str(x) for x in ProfileManager.PROFILE_LIST)}")


async def refresh_profile_list():
    ProfileManager.PROFILE_LIST.clear()
    await load_profiles_to_program()


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
