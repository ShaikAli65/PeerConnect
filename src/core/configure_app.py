import socket as soc
import configparser
import time
import requests
import src.avails.constants as const  # <--- This is the only import from avails/constants.py
from src.logs import *


def get_ip() -> str:
    """Retrieves the local IP address of the machine.

    Attempts to connect to a public DNS server (1.1.1.1) to obtain the local IP.
    If unsuccessful, falls back to using gethostbyname().

    Returns:
        str: The local IP address as a string.

    Raises:
        soc.error: If a socket error occurs during connection.
    """
    config_soc = soc.socket(const.IP_VERSION, const.PROTOCOL)
    config_soc.settimeout(1)
    config_ip = 'localhost'
    try:
        if const.IP_VERSION == soc.AF_INET:
            config_soc.connect(('www.google.com', 80))
            config_ip = config_soc.getsockname()[0]
        else:
            response = requests.get('https://api64.ipify.org?format=json')
            if response.status_code == 200:
                data = response.json()
                config_ip = data['ip']
    except soc.error as e:
        config_ip = soc.gethostbyname(soc.gethostname()) if const.IP_VERSION == soc.AF_INET else \
            soc.getaddrinfo(soc.gethostname(), None, const.IP_VERSION)[0][4][0]
        error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")
    finally:
        config_soc.close()
        return config_ip


def is_port_empty(port):
    try:
        with soc.socket(soc.AF_INET, soc.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            del s
            return True
    except soc.error:
        return False


def validate_ports() -> None:
    ports_list = [const.PORT_THIS, const.PORT_PAGE, const.PORT_REQ, const.PORT_FILE]
    for i in range(len(ports_list)):
        if is_port_empty(ports_list[i]):
            continue
        else:
            while not is_port_empty(ports_list[i]):
                ports_list[i] += 1
            error_log(f"Port is not empty. choosing another port: {ports_list[i]}")
    const.PORT_THIS, const.PORT_PAGE, const.PORT_REQ, const.PORT_FILE = ports_list
    return None


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
        print(line_format.format("PAGE_PORT  :", const.PORT_PAGE))
        time.sleep(const.anim_delay)
        print(line_format.format("PROTOCOL   :", const.PROTOCOL))
        time.sleep(const.anim_delay)
        print(line_format.format("IP_VERSION :", const.IP_VERSION))
        time.sleep(const.anim_delay)
        print(line_format.format("REQ_PORT   :", const.PORT_REQ))
        time.sleep(const.anim_delay)
        print("===============================================")
    return


def set_paths():
    const.PATH_CURRENT = os.path.join(os.getcwd())
    const.PATH_CONFIG = os.path.join(const.PATH_CURRENT, 'config.ini')
    const.PATH_LOG = os.path.join(const.PATH_CURRENT, 'src', 'logs')
    const.PATH_PAGE = os.path.join(const.PATH_CURRENT, 'src', 'webpage')
    downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
    const.PATH_DOWNLOAD = os.path.join(downloads_path, 'PeerConnect')
    if not os.path.exists(const.PATH_DOWNLOAD):
        os.makedirs(const.PATH_DOWNLOAD)

    # print("current path: ", const.PATH_CURRENT)
    # print("config path: ", const.PATH_CONFIG)
    # print("log path: ", const.PATH_LOG)
    # print("page path: ", const.PATH_PAGE)
    # print("download path: ", const.PATH_DOWNLOAD)


def set_constants() -> bool:
    """Sets global constants from values in the configuration file and directories.

    Reads configuration values from config.ini and sets global variables accordingly.
    Also sets directory paths for logs and the webpage.

    Returns:
        bool: True if configuration values were set successfully, False otherwise.
    """
    set_paths()
    clear_logs() if const.CLEARLOGSFLAG else None
    try:
        config_map = configparser.ConfigParser()
        config_map.read(const.PATH_CONFIG)
    except Exception as e:
        error_log(f"Error reading config.ini: {e} from set_constants() at line 75 in core/constants.py")
        return False
    const.USERNAME = config_map["CONFIGURATIONS"]['username']
    const.SERVER_IP = config_map['CONFIGURATIONS']['serverip']

    const.PAGE_SERVE_PORT = int(config_map['NERD_OPTIONS']['page_serve_port'])
    const.PORT_SERVER = int(config_map['CONFIGURATIONS']['server_port'])
    const.PORT_THIS = int(config_map['NERD_OPTIONS']['this_port'])
    const.PORT_PAGE = int(config_map['NERD_OPTIONS']['page_port'])
    const.PORT_REQ = int(config_map['NERD_OPTIONS']['req_port'])
    const.PORT_FILE = int(config_map['NERD_OPTIONS']['file_port'])

    validate_ports()
    time.sleep(0.04)
    const.PROTOCOL = soc.SOCK_STREAM if config_map['NERD_OPTIONS']['protocol'] == 'tcp' else soc.SOCK_DGRAM
    const.IP_VERSION = soc.AF_INET6 if config_map['NERD_OPTIONS']['ip_version'] == '6' else soc.AF_INET
    const.THIS_IP = get_ip()
    print_constants()
    if const.USERNAME == '' or const.SERVER_IP == '' or const.PORT_THIS == 0 or const.PORT_PAGE == 0 or const.PORT_SERVER == 0:
        error_log(f"Error reading config.ini from set_constants() at line 75 in core/constants.py")
        return False

    return True


def clear_logs():
    with open(os.path.join(const.PATH_LOG, 'error.logs'), 'w') as e:
        e.write('')
    with open(os.path.join(const.PATH_LOG, 'activity.logs'), 'w') as a:
        a.write('')
    with open(os.path.join(const.PATH_LOG, 'server.logs'), 'w') as s:
        s.write('')
    return


