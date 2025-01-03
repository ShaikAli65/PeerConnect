import configparser
import ipaddress
import os
import socket
from pathlib import Path

import src.avails.connect as connect
import src.avails.constants as const
from src.avails import connect, constants, use


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
        const.IP_VERSION = socket.AF_INET
        print(
            f"Error reading default_config.ini from {use.func_str(set_constants)}"
        )
        return False
    return True


def print_constants():
    print_string = (
        f'\n:configuration choices{"=" * 32}\n'
        f'{"USERNAME": <15} : {const.USERNAME: <10}\n'
        f'{"THIS_IP": <15} : {f"{const.THIS_IP}": <10}\n'
        f'{"PROTOCOL": <15} : {f"{const.PROTOCOL}": <10}\n'
        f'{"IP_VERSION": <15} : {ipaddress.ip_address(const.THIS_IP).version: <10}\n'
        f'{"SERVER_IP": <15} : {f"{const.SERVER_IP}": <10}\n'
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
    const.PATH_PROFILES = Path(const.PATH_CURRENT, 'profiles')
    const.PATH_LOG = Path(const.PATH_CURRENT, 'logs')
    const.PATH_PAGE = Path(const.PATH_CURRENT, 'src', 'webpage')
    const.PATH_CONFIG = Path(const.PATH_CURRENT, 'src', 'configurations', const.DEFAULT_CONFIG_FILE)
    const.PATH_LOG_CONFIG = Path(const.PATH_CURRENT, 'src', 'configurations', 'log_config.json')
    downloads_path = Path(os.path.expanduser('~'), 'Downloads')
    # check if the directory exists
    if not os.path.exists(downloads_path):
        downloads_path = Path(os.path.expanduser('~'), 'Desktop')

    const.PATH_DOWNLOAD = Path(os.path.join(downloads_path, 'PeerConnect'))
    try:
        os.makedirs(const.PATH_DOWNLOAD, exist_ok=True)
    except OSError as e:
        # error_log(f"Error creating directory: {e} from set_paths() at line 70 in core/constants.py")
        const.PATH_DOWNLOAD = os.path.join(const.PATH_CURRENT, 'fallbacks')


def validate_ports(ip):
    ports_list = [const.PORT_THIS, const.PORT_PAGE, const.PORT_REQ, ]
    for i, port in enumerate(ports_list):
        if not connect.is_port_empty(port, ip):
            ports_list[i] = connect.get_free_port(ip)
            use.echo_print(f"Port is not empty. choosing another port: {ports_list[i]}")
    const.PORT_THIS, const.PORT_PAGE, const.PORT_REQ = ports_list
