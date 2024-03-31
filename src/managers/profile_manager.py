import configparser
from pathlib import Path


from src.core import *


class ProfileManager:
    main_config = configparser.ConfigParser()

    def __init__(self, profiles_file, profile_data=''):
        ProfileManager.main_config.read(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE))
        self.profile_file_path = Path(const.PATH_PROFILES, profiles_file)
        if not profile_data == "":
            self.profiles = profile_data
        else:
            self.profiles = self.load_profile_data()

    def load_profile_data(self):
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
        self.profiles.setdefault(config_header, {}).update(new_settings)

        new_profile_path = Path(const.PATH_PROFILES, f"{self.username}.ini")
        if not prev_username == self.username:
            os.rename(self.profile_file_path, new_profile_path)
            self.__remove_from_main_config(prev_username)
            self.profile_file_path = new_profile_path
        self.save_profiles()

    def set_profile_data_from_file(self):
        self.profiles = self.load_profile_data()

    def save_profiles(self):
        config = configparser.ConfigParser()
        config.update({profile: settings for profile, settings in self.profiles.items()})

        with open(self.profile_file_path, 'w') as file:
            config.write(file)
        ProfileManager.__write_to_main_config(self.username)

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

    @classmethod
    def __write_to_main_config(cls, profile_name):
        main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)

        cls.main_config['USER_PROFILES'][profile_name] = f'{profile_name}.ini'
        with open(main_config_path, 'w') as file:
            cls.main_config.write(file)

    @classmethod
    def __remove_from_main_config(cls, profile_key):
        cls.main_config.remove_option('USER_PROFILES', profile_key)  # debug
        main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
        with open(main_config_path, 'w') as file:
            cls.main_config.write(file)

    @classmethod
    def delete_profile(cls, profile_username):
        profile_path = Path(const.PATH_PROFILES, f"{profile_username}.ini")
        if profile_path.is_file():
            profile_path.unlink(True)
        cls.__remove_from_main_config(profile_username)

    def __str__(self):
        return json.dumps(self.profiles)

    @property
    def username(self):
        return self.profiles['CONFIGURATIONS']['username']

    @property
    def server_ip(self):
        return self.profiles['CONFIGURATIONS']['server_ip']

    @property
    def server_port(self):
        return self.profiles['CONFIGURATIONS']['server_port']


def all_profiles() -> dict:
    """
    give all profiles available as key{username} :mapped to: their settings given by their ProfileManager object
    make sure that you definitely call :def load_profiles_to_program():,
     this function uses that list from const.PROFILE_LIST
    :return profiles:
    """
    return {profile.username: profile.load_profile_data() for profile in const.PROFILE_LIST}


def load_profiles_to_program() -> bool:
    if not os.path.exists(const.PATH_PROFILES):
        return False
    main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
    main_config = configparser.ConfigParser()
    main_config.read(main_config_path)
    const.PROFILE_LIST.extend([ProfileManager(settings) for settings in main_config['USER_PROFILES'].values()])
    return True


def set_selected_profile(profile: ProfileManager):
    const.USERNAME = profile.username
    const.SERVER_IP = profile.server_ip
    const.PORT_SERVER = int(profile.server_port)
    return
