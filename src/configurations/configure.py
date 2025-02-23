import asyncio
import configparser
import ipaddress
import os
import socket
from pathlib import Path

import src.avails.constants as const
from src.avails import connect
from src.configurations import logger as _logger


def print_constants():
    ip_version = ipaddress.ip_address(const.THIS_IP.ip).version
    print_string = (
        f'\n:configuration choices{"=" * 32}\n'
        f'{"USERNAME": <15} : {const.USERNAME: <10}\n'
        f'{"THIS_IP": <15} : {f"{const.THIS_IP}": <10}\n'
        f'{"PROTOCOL": <15} : {f"{const.PROTOCOL}": <10}\n'
        f'{"IP_VERSION": <15} : {ip_version: <10}\n'
        f'{"SERVER_IP": <15} : {f"{const.SERVER_IP}": <10}\n'
        f'{"MULTICAST_IP": <15} : {f"{const.MULTICAST_IP_v4 if ip_version == 4 else const.MULTICAST_IP_v6}": <10}\n'
        f'{"PORT_THIS": <15} : {const.PORT_THIS: <10}\n'
        f'{"SERVER_PORT": <15} : {const.PORT_SERVER: <10}\n'
        f'{"NETWORK_PORT": <15} : {const.PORT_NETWORK: <10}\n'
        f'{"PAGE_PORT": <15} : {const.PORT_PAGE: <10}\n'
        f'{"PORT_REQ": <15} : {const.PORT_REQ: <10}\n'
        f'{"=" * 56}\n'
    )
    with const.LOCK_PRINT:
        print('GLOBAL VERSION', const.VERSIONS['GLOBAL'])
        return print(print_string)

    # print("current path: ", const.PATH_CURRENT)
    # print("config path: ", const.PATH_PROFILES)
    # print("log path: ", const.PATH_LOG)
    # print("page path: ", const.PATH_PAGE)
    # print("download path: ", const.PATH_DOWNLOAD)


def set_paths():
    const.PATH_CURRENT = Path(os.getcwd())
    const.PATH_LOG = Path(const.PATH_CURRENT, 'logs')
    const.PATH_PAGE = Path(const.PATH_CURRENT, 'src', 'webpage')
    config_path = Path(const.PATH_CURRENT, 'configs')
    const.PATH_CONFIG_FILE = Path(config_path, const.DEFAULT_CONFIG_FILE_NAME)
    const.PATH_PROFILES = Path(config_path, 'profiles')
    const.PATH_LOG_CONFIG = Path(config_path, const.LOG_CONFIG_NAME)
    const.PATH_CONFIG = config_path

    downloads_path = Path(os.path.expanduser('~'), 'Downloads')
    # check if the directory exists
    if not os.path.exists(downloads_path):
        downloads_path = Path(os.path.expanduser('~'), 'Desktop')
    const.PATH_DOWNLOAD = Path(os.path.join(downloads_path, const.APP_NAME))

    try:
        os.makedirs(const.PATH_DOWNLOAD, exist_ok=True)
    except OSError as e:
        _logger.error(f"Error creating directory: {e} from set_paths()")
        const.PATH_DOWNLOAD = os.path.join(const.PATH_CURRENT, 'downloads')


async def load_configs():
    config_map = configparser.ConfigParser(allow_no_value=True)

    def _helper():
        try:
            config_map.read(const.PATH_CONFIG_FILE)
        except KeyError:
            write_default_configurations(const.PATH_CONFIG_FILE)
            config_map.read(const.PATH_CONFIG_FILE)

        if not Path(const.PATH_PROFILES, const.DEFAULT_PROFILE_NAME).exists():
            write_default_profile()

        if const.DEFAULT_PROFILE_NAME not in config_map['USER_PROFILES']:
            config_map.set('USER_PROFILES', const.DEFAULT_PROFILE_NAME)

        with open(const.PATH_CONFIG_FILE, 'w+') as fp:
            config_map.write(fp)  # noqa

    await asyncio.to_thread(_helper)

    set_constants(config_map)


def write_default_configurations(path):
    default_config_file = (
        '[NERD_OPTIONS]\n'
        'this_port = 48221\n'
        'page_port = 12260\n'
        'ip_version = 4\n'
        'protocol = tcp\n'
        'req_port = 35623\n'
        'page_serve_port = 40000\n'
        '\n'
        '[USER_PROFILES]\n'
        'admin\n'
        '[SELECTED_PROFILE]\n'
        'default_profile.ini\n'
    )
    with open(path, 'w+') as config_file:
        config_file.write(default_config_file)


def write_default_profile():
    default_profile_file = (
        '[USER]\n'
        'name = new user\n'
        'id = 1234'
        '\n'
        '[SERVER]\n'
        'port = 45000\n'
        'ip = 0.0.0.0\n'
        'id = 0\n'
        '[INTERFACE]'
    )
    with open(os.path.join(const.PATH_PROFILES, const.DEFAULT_PROFILE_NAME), 'w+') as profile_file:
        profile_file.write(default_profile_file)
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(const.PATH_CONFIG_FILE)
    parser.set('USER_PROFILES', const.DEFAULT_PROFILE_NAME)

    with open(const.PATH_CONFIG_FILE, 'w+') as fp:
        parser.write(fp)  # noqa


def set_constants(config_map: configparser.ConfigParser) -> bool:
    """Sets global constants from values in the configuration file and directories.

    Reads configuration values from default_config.ini and sets global variables accordingly.
    Also sets directory paths for logs and the webpage.

    Returns:
        bool: True if configuration values were flip successfully, False otherwise.
    """

    const.PORT_THIS = config_map.getint('NERD_OPTIONS', 'this_port')
    const.PORT_REQ = config_map.getint('NERD_OPTIONS', 'req_port')
    const.PORT_PAGE = config_map.getint('NERD_OPTIONS', 'page_port')
    const.PAGE_SERVE_PORT = config_map.getint('NERD_OPTIONS', 'page_serve_port')

    const.PROTOCOL = connect.TCPProtocol if config_map['NERD_OPTIONS']['protocol'] == 'tcp' else connect.UDPProtocol
    const.IP_VERSION = socket.AF_INET6 if config_map['NERD_OPTIONS']['ip_version'] == '6' else socket.AF_INET

    const.VERSIONS = {k.upper(): float(v) for k, v in config_map['VERSIONS'].items()}

    if const.IP_VERSION == socket.AF_INET6 and not socket.has_ipv6:
        _logger.warning(f"system does not support ipv6 ({socket.has_ipv6=}), using ipv4")
        const.IP_VERSION = socket.AF_INET

    if const.IP_VERSION == socket.AF_INET6:
        const.USING_IP_V6 = True
        const.USING_IP_V4 = False
        const.BIND_IP = const._BIND_IP_V6

    return True


def print_paths():
    print("\n".join(f"{x}={getattr(const, x)}" for x in dir(const) if x.startswith("PATH")))
