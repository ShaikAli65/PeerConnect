import asyncio
import configparser
import ipaddress
import json
import os
import random
import socket
import textwrap
from pathlib import Path

from kademlia.utils import digest

from src import net
from src.avails import const
from src.configurations import logger as _logger
from src.core.app import AppType
from src.net import TCPProtocol, UDPProtocol


def print_app(app):
    ip_version = ipaddress.ip_address(app.this_ip.ip).version
    print_string = textwrap.dedent(
        f"""        
        
        :configuration choices{"=" * 32}
        {"USERNAME": <15} : {app.this_remote_peer.username: <10}
        {"THIS_IP": <15} : {f"{app.this_ip}": <10}
        {"PROTOCOL": <15} : {f"{const.PROTOCOL}": <10}
        {"IP_VERSION": <15} : {ip_version: <10}
        {"SERVER_IP": <15} : {f"{const.SERVER_IP}": <10}
        {"MULTICAST_IP": <15} : {f"{const.MULTICAST_IP_v4 if ip_version == 4 else const.MULTICAST_IP_v6}": <10}
        {"PORT_THIS": <15} : {const.PORT_THIS: <10}
        {"SERVER_PORT": <15} : {const.PORT_SERVER: <10}
        {"NETWORK_PORT": <15} : {const.PORT_NETWORK: <10}
        {"PAGE_PORT": <15} : {const.PORT_PAGE: <10}
        {"PORT_REQ": <15} : {const.PORT_REQ: <10}
        {"=" * 56}
        """
    )
    with const.LOCK_PRINT:
        print('GLOBAL VERSION', const.VERSIONS['GLOBAL'])
        return print(print_string)


def _get_local_appdata_path():
    if const.IS_WINDOWS:
        return Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"), const.APP_NAME)
    else:
        return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"), const.APP_NAME)


def set_paths():
    """
    Current Setup
    * log config is present at app-level
    * basic config is present at local user data directories
    * all logs are written into local user data directories
    * webpage at app-level
    """
    path_app_data = _get_local_appdata_path()
    path_app_data.mkdir(exist_ok=True, parents=True)
    config_path = Path(path_app_data, 'configs')
    config_path.mkdir(exist_ok=True)

    const.PATH_LOG = Path(path_app_data, 'logs')

    const.PATH_CURRENT = Path(os.getcwd())
    const.PATH_LOG.mkdir(exist_ok=True)
    const.PATH_PAGE = Path(const.PATH_CURRENT, 'webpage')
    const.PATH_LOG_CONFIG = Path(const.PATH_CURRENT, 'configs', const.LOG_CONFIG_NAME)

    const.PATH_CONFIG_FILE = Path(config_path, const.DEFAULT_CONFIG_FILE_NAME)
    const.PATH_PROFILES = Path(config_path, 'profiles')
    const.PATH_PROFILES.mkdir(exist_ok=True)
    const.PATH_CONFIG = config_path

    downloads_path = Path(Path.home(), 'Downloads')
    # check if the directory exists
    if not downloads_path.exists():
        downloads_path = Path(Path.home(), 'Desktop')

    const.PATH_DOWNLOAD = Path(os.path.join(downloads_path, const.APP_NAME))

    try:
        os.makedirs(const.PATH_DOWNLOAD, exist_ok=True)
    except OSError as e:
        _logger.error(f"Error creating directory: {e} from set_paths()")
        const.PATH_DOWNLOAD = Path(path_app_data, 'downloads')
        const.PATH_DOWNLOAD.mkdir(exist_ok=True)

    print_paths()


async def load_configs(app: AppType):
    config_map = configparser.ConfigParser(allow_no_value=True)

    def _helper():
        try:
            _logger.debug(f"reading config file from : {const.PATH_CONFIG_FILE}")
            config_map.read(const.PATH_CONFIG_FILE)
            # access required keys
            _ = config_map['USER_PROFILES']
            _ = config_map['NERD_OPTIONS']
            _ = config_map['VERSIONS']
            _ = config_map['SELECTED_PROFILE']
        except KeyError:
            _write_default_configurations(const.PATH_CONFIG_FILE)
            config_map.read(const.PATH_CONFIG_FILE)

        if not any(tuple(Path(const.PATH_PROFILES).glob("*.ini"))):
            _write_default_profile(Path(const.PATH_PROFILES, const.DEFAULT_PROFILE_NAME), config_map)

        with open(const.PATH_CONFIG_FILE, 'w+') as fp:
            config_map.write(fp)  # noqa

    async def finalize_config():

        def _finalize_config_helper():
            _logger.debug(f"writing configurations to {const.PATH_CONFIG_FILE}")

            config_dict = {section: dict(config_map.items(section)) for section in config_map.sections()}
            _logger.debug(json.dumps(config_dict, indent=4))

            with open(const.PATH_CONFIG_FILE, 'w+') as fp:
                config_map.write(fp)  # noqa
                # write the final state of configuration when exiting application

        return await asyncio.to_thread(_finalize_config_helper)

    await asyncio.to_thread(_helper)
    set_constants(config_map)
    app.current_config = config_map
    app.exit_stack.push_async_callback(finalize_config)


def _write_default_configurations(path):
    default_config_file = textwrap.dedent(
        f"""
        [NERD_OPTIONS]
        ip_version = {4 if const.IP_VERSION == socket.AF_INET else 6}
        protocol = tcp
        this_port = {const.PORT_THIS}
        req_port = {const.PORT_REQ}
        page_port = {const.PORT_PAGE}
        page_serve_port = {const.PORT_PAGE_SERVE}
        
        [VERSIONS]
        global = 1.1
        rp = 1.1
        fo = 1.1
        do = 1.1
        wire = 1.1
        
        [USER_PROFILES]
        {const.DEFAULT_PROFILE_NAME}
        
        [SELECTED_PROFILE]
        {const.DEFAULT_PROFILE_NAME}
        """
    )
    with open(path, 'w+') as config_file:
        config_file.write(default_config_file)


def _write_default_profile(profile_path, config_map):
    default_profile_file = textwrap.dedent(
        f"""
        [USER]
        name = new user
        id = {int.from_bytes(digest(random.randbytes(160)))}
        
        [INTERFACE]
        
        [TRANSFERS AGREED]
        """
    )
    with open(profile_path, 'w+') as profile_file:
        profile_file.write(default_profile_file)

    config_map.set('USER_PROFILES', profile_path.name)


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

    const.PROTOCOL = TCPProtocol if config_map['NERD_OPTIONS']['protocol'] == 'tcp' else UDPProtocol
    const.IP_VERSION = socket.AF_INET6 if config_map['NERD_OPTIONS']['ip_version'] == '6' else socket.AF_INET

    const.VERSIONS = {k.upper(): float(v) for k, v in config_map['VERSIONS'].items()}

    if const.IP_VERSION == socket.AF_INET6:
        if socket.has_ipv6:
            # this still does not assure that we have valid ipv6 addresses to avaliable interfaces
            if len(net.get_interfaces(socket.AF_INET6)) <= 0:
                _logger.warning(f"system does not have a valid interface with ipv6 address, using ipv4")
                const.IP_VERSION = socket.AF_INET

    if const.IP_VERSION == socket.AF_INET6:
        const.USING_IP_V6 = True
        const.USING_IP_V4 = False
    const.BIND_IP = const._BIND_IP_V6

    return True


def print_paths():
    print(*(f"{x}={getattr(const, x)}" for x in dir(const) if x.startswith("PATH")), sep="\n")
