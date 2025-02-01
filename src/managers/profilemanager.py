import configparser
import os
import time
from pathlib import Path
from typing import Optional, Union

from src.avails import const


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
        else:
            self.profile_data: dict[str, dict] = self.get_profile_data()

    def get_profile_data(self) -> dict:
        """
        Performs a structural pattern matching
        :raises ValueError: if required keys were not found
        :return profiles_data: if all required keys were found
        """

        profile_data = self.__load_profile_data()
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
            }:
                return profile_data
            case _:
                self.__raise_error()

    def __load_profile_data(self) -> dict:
        try:
            config = configparser.ConfigParser()
            config.read(self.profile_file_path)
            return {
                section: dict(config.items(section)) for section in config.sections()
            }
        except FileNotFoundError:
            return {}

    def edit_profile(self, config_header, new_settings: dict):
        """
        Accepts a dictionary of new settings and updates the profile with the new settings
        mapped to respective config_header
        :param config_header:
        :param new_settings:
        :return:
        """
        prev_username = self.username
        self.profile_data.setdefault(config_header, {}).update(new_settings)
        if not prev_username == self.username:
            new_profile_path = Path(
                const.PATH_PROFILES, self.__uniquify(self.username) + ".ini"
            )
            os.rename(self.profile_file_path, new_profile_path)
            self.__remove_from_main_config(self.profile_file_path.name)
            self.__write_to_main_config(new_profile_path.name)
            self.profile_file_path = new_profile_path
        self.save_profiles()

    def set_profile_data_from_file(self):
        self.profile_data = self.__load_profile_data()

    def save_profiles(self):
        config = configparser.ConfigParser()
        config.update(
            {profile: settings for profile, settings in self.profile_data.items()}
        )
        with open(self.profile_file_path, "w") as file:
            config.write(file)

    def __raise_error(self):
        raise LookupError(
            f"something wrong in profile data\n:\tprofile at {self.profile_file_path}\ndata:"
        )

    @classmethod
    def add_profile(cls, profile_name, settings: dict):
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
        with open(profile_path, "w") as file:
            config.write(file)
        cls.__write_to_main_config(profile_path.name)
        cls.PROFILE_LIST.append(cls(profile_path))

    @classmethod
    def __write_to_main_config(cls, file_name):
        cls._main_config.set("USER_PROFILES", file_name)
        with open(const.PATH_CONFIG, "w") as file:
            cls._main_config.write(file)

    @classmethod
    def __remove_from_main_config(cls, profile_key):
        cls._main_config.remove_option("USER_PROFILES", profile_key)  # debug
        with open(const.PATH_CONFIG, "w") as file:
            cls._main_config.write(file)

    @classmethod
    def write_selected_profile(cls, profile):
        cls._main_config.remove_section("SELECTED_PROFILE")
        with open(const.PATH_CONFIG, "w") as file:
            cls._main_config.write(file)

        cls._main_config.add_section("SELECTED_PROFILE")
        cls._main_config.set("SELECTED_PROFILE", profile.file_name)
        with open(const.PATH_CONFIG, "w") as file:
            cls._main_config.write(file)

    @classmethod
    def delete_profile(cls, profile_file_name):
        profile_path = Path(
            const.PATH_PROFILES, profile_file_name
        )
        if profile_path.is_file():
            try:
                profile_path.unlink(True)
            except os.error as e:
                # error_log(f"deletion error for profile {profile_file_name} exp:{e}")
                ...
        cls.__remove_from_main_config(profile_path.name)

    def __repr__(self):
        return f"<Profile name={self.username} file_path={self.profile_file_path}>"

    @property
    def username(self):
        return self.profile_data["USER"]["name"]

    @property
    def id(self) -> int:
        return self.profile_data["USER"]["id"]

    @property
    def file_name(self):
        return self.profile_file_path.name

    @property
    def server_ip(self):
        return self.profile_data["SERVER"]["ip"]

    @property
    def server_port(self):
        return int(self.profile_data["SERVER"]["port"])

    @staticmethod
    def __uniquify(username):
        return f"{username}{int(time.time() * 10)}"

    @classmethod
    def prev_selected_profile_file_name(cls):
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
            f"\tserver_port={self.server_port}\n"
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


def load_profiles_to_program():
    if not os.path.exists(const.PATH_PROFILES):
        raise EnvironmentError("profiles path not found")

    main_config = configparser.ConfigParser(allow_no_value=True)
    main_config.read(const.PATH_CONFIG)

    ProfileManager._main_config = main_config
    for profile_id in main_config["USER_PROFILES"]:
        try:
            profile = ProfileManager(profile_id)
            ProfileManager.PROFILE_LIST.append(profile)
        except LookupError:
            ProfileManager.delete_profile(profile_id)
    return True


def refresh_profile_list():
    ProfileManager.PROFILE_LIST.clear()
    load_profiles_to_program()


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


def set_current_profile(profile):
    global _current_profile
    _current_profile = profile
    ProfileManager.write_selected_profile(profile)


def get_current_profile() -> ProfileManager:
    global _current_profile
    return _current_profile
