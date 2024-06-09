import os
import socket
import socket as soc
import configparser

from logs import error_log

import src.avails.constants as const  # <--- This is the only import from avails/constants.py
from logs import *

from src.avails import constants
from src.managers.profile_manager import ProfileManager


def set_constants(config_map: configparser.ConfigParser) -> bool:
    """Sets global constants from values in the configuration file and directories.

    Reads configuration values from default_config.ini and sets global variables accordingly.
    Also sets directory paths for logs and the webpage.

    Returns:
        bool: True if configuration values were flip successfully, False otherwise.
    """

    const.PAGE_SERVE_PORT = config_map.getint('NERD_OPTIONS', 'page_serve_port')
    const.PORT_THIS = config_map.getint('NERD_OPTIONS', 'this_port')
    const.PORT_PAGE_DATA = config_map.getint('NERD_OPTIONS', 'page_port')
    const.PORT_REQ = config_map.getint('NERD_OPTIONS', 'req_port')
    const.PORT_FILE = config_map.getint('NERD_OPTIONS', 'file_port')
    const.PORT_PAGE_SIGNALS = config_map.getint('NERD_OPTIONS', 'page_port_signals')
    const.PROTOCOL = soc.SOCK_STREAM if config_map['NERD_OPTIONS']['protocol'] == 'tcp' else soc.SOCK_DGRAM
    const.IP_VERSION = soc.AF_INET6 if config_map['NERD_OPTIONS']['ip_version'] == '6' else soc.AF_INET
    if const.IP_VERSION == soc.AF_INET6 and not socket.has_ipv6:
        const.IP_VERSION = soc.AF_INET
    if const.USERNAME == '' or const.PORT_THIS == 0 or const.PORT_PAGE_DATA == 0 or const.PORT_SERVER == 0:
        error_log(
            f"Error reading default_config.ini from set_constants() in {set_constants.__name__}()/{set_constants.__code__.co_filename}")
        return False

    return True


def print_constants():
    line = "{:<15} {:<10}"
    with const.LOCK_PRINT:
        print('\n:configuration choices============================\n'
              f'{line.format("USERNAME", const.USERNAME)}\n'
              f'{line.format("THIS_IP", const.THIS_IP)}\n'
              f'{line.format("PORT_THIS", const.PORT_THIS)}\n'
              f'{line.format("SERVER_IP", const.SERVER_IP)}\n'
              f'{line.format("SERVER_PORT", const.PORT_SERVER)}\n'
              f'{line.format("PAGE_DATA_PORT", const.PORT_PAGE_DATA)}\n'
              f'{line.format("PROTOCOL", const.PROTOCOL)}\n'
              f'{line.format("IP_VERSION", const.IP_VERSION)}\n'
              f'{line.format("PORT_REQ", const.PORT_REQ)}\n'
              '===================================================\n'
              )
    return
    #
    # print("current path: ", const.PATH_CURRENT)
    # print("config path: ", const.PATH_PROFILES)
    # print("log path: ", const.PATH_LOG)
    # print("page path: ", const.PATH_PAGE)
    # print("download path: ", const.PATH_DOWNLOAD)


def set_selected_profile(profile: ProfileManager):
    const.USERNAME = profile.username
    const.SERVER_IP = profile.server_ip
    const.PORT_SERVER = int(profile.server_port)
    const.THIS_OBJECT.username = profile.username
    return


def set_paths():
    const.PATH_CURRENT = os.path.join(os.getcwd())
    const.PATH_PROFILES = os.path.join(const.PATH_CURRENT, 'profiles')
    const.PATH_LOG = os.path.join(const.PATH_CURRENT, 'logs')
    const.PATH_PAGE = os.path.join(const.PATH_CURRENT, 'src', 'webpage')
    const.PATH_CONFIG = os.path.join(const.PATH_CURRENT, 'src', 'configurations', const.DEFAULT_CONFIG_FILE)
    downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
    # check if the directory exists
    if not os.path.exists(downloads_path):
        downloads_path = os.path.join(os.path.expanduser('~'), 'Desktop')

    const.PATH_DOWNLOAD = os.path.join(downloads_path, 'PeerConnect')
    try:
        os.makedirs(const.PATH_DOWNLOAD, exist_ok=True)
    except OSError as e:
        error_log(f"Error creating directory: {e} from set_paths() at line 70 in core/constants.py")
        const.PATH_DOWNLOAD = os.path.join(const.PATH_CURRENT, 'fallbacks')
