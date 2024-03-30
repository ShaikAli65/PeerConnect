import json
import configparser
import os
from src.avails import constants as const


class ProfileManager:
    def __init__(self, profiles_file, profile_data=''):
        self.profiles_file = profiles_file
        if not profile_data == "":
            self.profiles = profile_data
        else:
            self.profiles = self.load_profile_data()

    def load_profile_data(self):
        try:
            config = configparser.ConfigParser()
            config.read(self.profiles_file)
            return {section: dict(config.items(section)) for section in config.sections()}
        except FileNotFoundError:
            return {}

    def edit_profile(self, config_header, new_settings):
        """
        Accepts a dictionary of new settings and updates the profile with the new settings
        mapped to respective config_header
        :param config_header:
        :param new_settings:
        :return:
        """
        if config_header in self.profiles:
            self.profiles[config_header].update(new_settings)
        else:
            self.profiles[config_header] = new_settings

        self.save_profiles()

    def set_profile_data_from_file(self):
        self.profiles = self.load_profile_data()

    def save_profiles(self):
        config = configparser.ConfigParser()
        for profile, settings in self.profiles.items():
            config[profile] = settings
        with open(self.profiles_file, 'w') as file:
            config.write(file)

    @classmethod
    def add_profile(cls, profile_name, settings:dict):
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
        main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
        main_config = configparser.ConfigParser()
        main_config.read(main_config_path)
        main_config['USER_PROFILES'][profile_name] = f'{profile_name}.ini'
        with open(main_config_path, 'w') as file:
            main_config.write(file)

    @classmethod
    def delete_profile(cls, profile_username):
        if os.path.exists(os.path.join(const.PATH_PROFILES, f"{profile_username}.ini")):
            os.remove(os.path.join(const.PATH_PROFILES, f"{profile_username}.ini"))
        main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
        main_config = configparser.ConfigParser()
        main_config.read(main_config_path)
        main_config.remove_option('USER_PROFILES', profile_username)
        with open(main_config_path, 'w') as file:
            main_config.write(file)

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

    @property
    def path(self):
        return os.path.join(self.profiles_file)


def all_profiles():
    main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
    main_config = configparser.ConfigParser(defaults=None)
    main_config.read(main_config_path)
    profiles = {}
    for _, profile_file_name in main_config['USER_PROFILES'].items():
        profile_path = os.path.join(const.PATH_PROFILES, profile_file_name)
        profile_manager = ProfileManager(profile_path)
        profiles[profile_manager.username] = profile_manager.load_profile_data()
    return profiles


def load_profiles_to_program():
    if not os.path.exists(const.PATH_PROFILES):
        return False
    main_config_path = os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE)
    main_config = configparser.ConfigParser()
    main_config.read(main_config_path)
    for profile in main_config['USER_PROFILES']:
        profile_path = os.path.join(const.PATH_PROFILES, main_config['USER_PROFILES'][profile])
        profile = ProfileManager(profile_path)
        const.PROFILE_LIST.append(profile)
    return True


def set_selected_profile(profile:ProfileManager):
    const.USERNAME = profile.username
    const.SERVER_IP = profile.server_ip
    const.PORT_SERVER = int(profile.server_port)
    return
