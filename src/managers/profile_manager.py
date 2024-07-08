import configparser
from datetime import datetime
from pathlib import Path

from src.core import *


def uniquify(profile_name):
    # import uuid
    # random_str = str(uuid.uuid4())
    random_str = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{profile_name}{random_str}.ini"


class ProfileManager:
    main_config = configparser.ConfigParser(allow_no_value=True)
    """
    This class used to contain a profile instance of profiles 
    it is recommended to discard this class's object if an error is raised somewhere in using 
    as it can lead to unexpected behaviour
    """
    def __init__(self, profiles_file, *, profile_data=None):
        self.profile_file_path = Path(const.PATH_PROFILES, profiles_file)
        if profile_data is not None:
            self.profile_data = profile_data
        else:
            self.profile_data = self.get_profile_data()

    def get_profile_data(self) -> dict:
        """
        Performs a structural pattern matching
        :raises ValueError: if required keys were not found
        :return profiles_data: if all required keys were found
        """

        profile_data = self.__load_profile_data()
        match profile_data:
            case {
                'SERVER': {
                    'ip': _,
                    'port': _
                },
                'USER': {
                    'name': _
                }
            }: return profile_data
            case _:
                self.__raise_error()

    def __load_profile_data(self) -> dict:
        try:
            config = configparser.ConfigParser()
            config.read(self.profile_file_path)
            return {section: dict(config.items(section)) for section in config.sections()}
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
            new_profile_path = Path(const.PATH_PROFILES, uniquify(self.username))
            os.rename(self.profile_file_path, new_profile_path)
            self.__remove_from_main_config(self.profile_file_path.name)
            self.__write_to_main_config(new_profile_path.name)
            self.profile_file_path = new_profile_path
        self.save_profiles()

    def set_profile_data_from_file(self):
        self.profile_data = self.__load_profile_data()

    def save_profiles(self):
        config = configparser.ConfigParser()
        config.update({profile: settings for profile, settings in self.profile_data.items()})
        with open(self.profile_file_path, 'w') as file:
            config.write(file)

    def __raise_error(self):
        raise LookupError(f"something wrong in profile data\n:\tprofile at {self.profile_file_path}\ndata:")

    @classmethod
    def add_profile(cls, profile_name, settings: dict):
        """
         Adds profile into application with settings provided as a dictionary mapped to respective headers
        :param profile_name:
        :param settings:
        :return:
        """
        profile_path = Path(const.PATH_PROFILES, uniquify(profile_name))
        config = configparser.ConfigParser()
        for section, setting in settings.items():
            config[section] = setting
        with open(profile_path, 'w') as file:
            config.write(file)
        cls.__write_to_main_config(profile_path.name)
        const.PROFILE_LIST.append(cls(profile_path))

    @classmethod
    def __write_to_main_config(cls, file_name):
        cls.main_config.set('USER_PROFILES',file_name)
        with open(const.PATH_CONFIG, 'w') as file:
            cls.main_config.write(file)

    @classmethod
    def __remove_from_main_config(cls, profile_key):
        cls.main_config.remove_option('USER_PROFILES', profile_key)  # debug
        with open(const.PATH_CONFIG, 'w') as file:
            cls.main_config.write(file)

    @classmethod
    def delete_profile(cls, profile_file_name):
        profile_path = Path(const.PATH_PROFILES, profile_file_name)  # if not profile_username.endswith('.ini') else profile_username)
        if profile_path.is_file():
            try:
                profile_path.unlink(True)
            except os.error as e:
                error_log(f"deletion error for profile {profile_file_name} exp:{e}")
        cls.__remove_from_main_config(profile_path.name)

    def __repr__(self):
        return f'<Profile name={self.username} file_path={self.profile_file_path}>'

    @property
    def username(self):
        return self.profile_data['USER']['name']

    @property
    def file_name(self):
        return self.profile_file_path.name

    @property
    def server_ip(self):
        return self.profile_data['SERVER']['ip']

    @property
    def server_port(self):
        print("adfar")  # debug
        return self.profile_data['SERVER']['port']

    def __eq__(self, other):
        if isinstance(other, dict):
            return (self.username == other['USER']['name']
                    and self.server_ip == other['SERVER']['ip'])
        else:
            return self is other


def all_profiles() -> dict:
    """
    give all profiles available as key{username} :mapped to: their settings given by their ProfileManager object
    make sure that you definitely call :def load_profiles_to_program():,
     this function uses that list from const.PROFILE_LIST
    :return profiles:
    """
    return {profile.file_name: profile.profile_data for profile in const.PROFILE_LIST}


def load_profiles_to_program():
    if not os.path.exists(const.PATH_PROFILES):
        return False

    main_config = configparser.ConfigParser(allow_no_value=True)
    main_config.read(const.PATH_CONFIG)

    ProfileManager.main_config = main_config
    for profile_id in main_config['USER_PROFILES']:
        try:
            profile = ProfileManager(profile_id)
            const.PROFILE_LIST.append(profile)
        except LookupError:
            ProfileManager.delete_profile(profile_id)
    return True


def get_profile_from_profile_file_name(profile_file_name) -> Union[ProfileManager, None]:
    """
    Retrieves profile object from list given username
    :param profile_file_name:
    """
    return next((profile for profile in const.PROFILE_LIST if profile.file_name == profile_file_name), None)
