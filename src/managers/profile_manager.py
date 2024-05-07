import configparser
from pathlib import Path

from src.core import *


class ProfileManager:
    main_config = configparser.ConfigParser()
    """
    This class used to contain a profile instance of profiles 
    it is recommended to discard this class's object if an error is raised somewhere in using 
    as it can lead to unexpected behaviour
    """
    def __init__(self, profiles_file, *, profile_data=''):
        self.profile_file_path = Path(const.PATH_PROFILES, profiles_file)
        if not profile_data == "":
            self.profile_data = profile_data
        else:
            self.profile_data: dict = self.get_profile_data()

    def get_profile_data(self) -> dict:
        profile_data: dict = self.__load_profile_data()
        if not ('CONFIGURATIONS' in profile_data.keys()):
            self.__raise_error()
        #  more look up 's if needed

        configuration_key: dict = profile_data['CONFIGURATIONS']
        for check_key in ['server_ip', 'username', 'server_port']:  # add more keys here, under configurations
            if check_key not in configuration_key.keys():
                self.__raise_error()

        return profile_data

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
        new_profile_path = Path(const.PATH_PROFILES, f"{self.username}.ini")
        if not prev_username == self.username:
            os.rename(self.profile_file_path, new_profile_path)
            self.__remove_from_main_config(self.profile_file_path.name)
            self.profile_file_path = new_profile_path
        self.save_profiles()

    def set_profile_data_from_file(self):
        self.profile_data = self.__load_profile_data()

    def save_profiles(self):
        config = configparser.ConfigParser()
        config.update({profile: settings for profile, settings in self.profile_data.items()})

        with open(self.profile_file_path, 'w') as file:
            config.write(file)
        ProfileManager.__write_to_main_config(self.username)

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
        profile_path = os.path.join(const.PATH_PROFILES, f'{profile_name}.ini')
        config = configparser.ConfigParser()
        for section, setting in settings.items():
            config[section] = setting
        with open(profile_path, 'w') as file:
            config.write(file)
        cls.__write_to_main_config(profile_name)
        const.PROFILE_LIST.append(ProfileManager(profile_path))

    @classmethod
    def __write_to_main_config(cls, profile_name):
        main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
        cls.main_config['USER_PROFILES'][f'{profile_name}.ini'] = '.'
        with open(main_config_path, 'w') as file:
            cls.main_config.write(file)

    @classmethod
    def __remove_from_main_config(cls, profile_key):
        cls.main_config.remove_option('USER_PROFILES', profile_key)  # debug
        main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
        with open(main_config_path, 'w') as file:
            cls.main_config.write(file)

    @classmethod
    def delete_profile(cls, profile_username: str):
        profile_path = Path(const.PATH_PROFILES,
                            f"{profile_username}.ini" if not profile_username.endswith('.ini') else profile_username)
        if profile_path.is_file():
            try:
                profile_path.unlink(True)
            except os.error as e:
                error_log(f"deletion error for profile {profile_username}:{e}")
        cls.__remove_from_main_config(profile_path.name)

    def __str__(self):
        return json.dumps(self.profile_data)

    @property
    def username(self):
        return self.profile_data['CONFIGURATIONS']['username']

    @property
    def server_ip(self):
        return self.profile_data['CONFIGURATIONS']['server_ip']

    @property
    def server_port(self):
        return self.profile_data['CONFIGURATIONS']['server_port']


def all_profiles() -> dict:
    """
    give all profiles available as key{username} :mapped to: their settings given by their ProfileManager object
    make sure that you definitely call :def load_profiles_to_program():,
     this function uses that list from const.PROFILE_LIST
    :return profiles:
    """
    return {profile.username: profile.profile_data for profile in const.PROFILE_LIST}


def load_profiles_to_program() -> bool:
    if not os.path.exists(const.PATH_PROFILES):
        return False

    main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
    main_config = configparser.ConfigParser()
    main_config.read(main_config_path)

    ProfileManager.main_config = main_config
    profile_list_to_verify = []
    for profile_id in main_config['USER_PROFILES'].keys():
        try:
            profile = ProfileManager(profile_id)
            profile_list_to_verify.append(profile)
        except LookupError:
            ProfileManager.delete_profile(profile_id)

    const.PROFILE_LIST.extend(profile_list_to_verify)
    return True


def set_selected_profile(profile: ProfileManager):
    const.USERNAME = profile.username
    const.SERVER_IP = profile.server_ip
    const.PORT_SERVER = int(profile.server_port)
    return
