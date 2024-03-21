import socket as soc
import configparser
import time
import src.avails.constants as const  # <--- This is the only import from avails/constants.py
from logs import *


def set_constants(config_map:configparser) -> bool:
    """Sets global constants from values in the configuration file and directories.

    Reads configuration values from default_config.ini and sets global variables accordingly.
    Also sets directory paths for logs and the webpage.

    Returns:
        bool: True if configuration values were set successfully, False otherwise.
    """

    const.PAGE_SERVE_PORT = int(config_map['NERD_OPTIONS']['page_serve_port'])
    const.PORT_THIS = int(config_map['NERD_OPTIONS']['this_port'])
    const.PORT_PAGE_DATA = int(config_map['NERD_OPTIONS']['page_port'])
    const.PORT_REQ = int(config_map['NERD_OPTIONS']['req_port'])
    const.PORT_FILE = int(config_map['NERD_OPTIONS']['file_port'])

    const.PROTOCOL = soc.SOCK_STREAM if config_map['NERD_OPTIONS']['protocol'] == 'tcp' else soc.SOCK_DGRAM
    const.IP_VERSION = soc.AF_INET6 if config_map['NERD_OPTIONS']['ip_version'] == '6' else soc.AF_INET

    # print_constants()
    if const.USERNAME == '' or const.SERVER_IP == '' or const.PORT_THIS == 0 or const.PORT_PAGE_DATA == 0 or const.PORT_SERVER == 0:
        error_log(f"Error reading default_config.ini from set_constants() in {set_constants.__name__}()/{set_constants.__code__.co_filename}")
        return False

    return True


def print_constants():
    line_format = "{:<15} {:<10}"
    with const.LOCK_PRINT:
        print(':configuration choices=========================')
        time.sleep(const.anim_delay)
        print(line_format.format("USERNAME   :", const.USERNAME))
        time.sleep(const.anim_delay)
        print(line_format.format("YOUR IP    :", const.THIS_IP))
        print(line_format.format("THIS_PORT  :", const.PORT_THIS))
        time.sleep(const.anim_delay)
        print(line_format.format("SERVER_IP  :", const.SERVER_IP))
        time.sleep(const.anim_delay)
        print(line_format.format("SERVER_PORT:", const.PORT_SERVER))
        time.sleep(const.anim_delay)
        print(line_format.format("PAGE_PORT  :", const.PORT_PAGE_DATA))
        time.sleep(const.anim_delay)
        print(line_format.format("PROTOCOL   :", const.PROTOCOL))
        time.sleep(const.anim_delay)
        print(line_format.format("IP_VERSION :", const.IP_VERSION))
        time.sleep(const.anim_delay)
        print(line_format.format("REQ_PORT   :", const.PORT_REQ))
        time.sleep(const.anim_delay)
        print("===============================================")
    return
    #
    # print("current path: ", const.PATH_CURRENT)
    # print("config path: ", const.PATH_PROFILES)
    # print("log path: ", const.PATH_LOG)
    # print("page path: ", const.PATH_PAGE)
    # print("download path: ", const.PATH_DOWNLOAD)
