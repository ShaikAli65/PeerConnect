from src.core import *
from src.configurations.configure_app import set_constants
import configparser
import requests
import socket as soc


def initiate():
    const.THIS_IP = get_ip()
    clear_logs() if const.CLEARLOGSFLAG else None

    config_map = configparser.ConfigParser()
    try:
        config_map.read(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE))
    except KeyError:
        load_defaults()
        config_map.read(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE))
    set_constants(config_map)
    validate_ports()


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
    config_soc.settimeout(2)
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
        error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")
        config_ip = soc.gethostbyname(soc.gethostname()) if const.IP_VERSION == soc.AF_INET else \
            soc.getaddrinfo(soc.gethostname(), None, const.IP_VERSION)[0][4][0]
    finally:
        config_soc.close()
        return config_ip


def set_paths():
    const.PATH_CURRENT = os.path.join(os.getcwd())
    const.PATH_PROFILES = os.path.join(const.PATH_CURRENT, 'profiles')
    const.PATH_LOG = os.path.join(const.PATH_CURRENT, 'logs')
    const.PATH_PAGE = os.path.join(const.PATH_CURRENT, 'src', 'webpage')
    downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
    const.PATH_DOWNLOAD = os.path.join(downloads_path, 'PeerConnect')
    if not os.path.exists(const.PATH_DOWNLOAD):
        os.makedirs(const.PATH_DOWNLOAD)


def clear_logs():
    with open(os.path.join(const.PATH_LOG, 'error.logs'), 'w') as e:
        e.write('')
    with open(os.path.join(const.PATH_LOG, 'activity.logs'), 'w') as a:
        a.write('')
    with open(os.path.join(const.PATH_LOG, 'server.logs'), 'w') as s:
        s.write('')
    return


def load_defaults():
    default_config_file = (
        '[NERD_OPTIONS]'
        'this_port = 48221'
        'page_port = 12260'
        'ip_version = 4'
        'protocol = tcp'
        'req_port = 35623'
        'file_port = 35621'
        'page_serve_port = 40000'
        '\n'
        '[USER_PROFILES]'
        'admin = admin.ini'
    )
    default_profile_file = (
        '[CONFIGURATIONS]'
        'username = admin'
        'server_port = 45000'
        'serverip = 0.0.0.0'
    )

    with open(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE), 'w+') as config_file:
        config_file.write(default_config_file)
    with open(os.path.join(const.PATH_PROFILES, 'admin.ini'), 'w+') as profile_file:
        profile_file.write(default_profile_file)


def is_port_empty(port):
    try:
        with soc.socket(soc.AF_INET, soc.SOCK_STREAM) as s:
            s.bind((const.THIS_IP, port))
            del s
            return True
    except soc.error:
        return False


def validate_ports() -> None:
    ports_list = [const.PORT_THIS, const.PORT_PAGE_DATA, const.PORT_PAGE_SIGNALS, const.PORT_REQ,
                  const.PORT_FILE]
    for i in range(len(ports_list)):
        if is_port_empty(ports_list[i]):
            continue
        else:
            while not is_port_empty(ports_list[i]):
                ports_list[i] += 1
            error_log(f"Port is not empty. choosing another port: {ports_list[i]}")
    const.PORT_THIS, const.PORT_PAGE_DATA, const.PORT_PAGE_SIGNALS, const.PORT_REQ, const.PORT_FILE = ports_list
    return None
