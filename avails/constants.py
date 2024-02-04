import socket
import socket as soc
import threading
import configparser
import time

import requests
from logs import *

USERNAME = ''
THIS_PORT = 0
PAGE_PORT = 0
SERVER_PORT = 0
SERVER_IP = ''
FILE_PORT = 45210
REQ_PORT = 35896
CURRENT_DIR = ''
LOG_DIR = ''
CONFIG_PATH = ''
PAGE_PATH = ''
DOWNLOAD_PATH = ''
THIS_IP = ''

IP_VERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM
FORMAT = 'utf-8'
count_of_user_id = 0
user_id_lock = threading.Lock()
anim_delay = 0
MAX_CALL_BACKS = 6

OBJ = None
OBJ_THREAD = None
REQUESTS_THREAD = None
REMOTE_OBJECT = None
SERVER_THREAD = None
ACTIVE_PEERS = []
PAGE_HANDLE_CALL = threading.Event()
SAFE_LOCK_FOR_PAGE = False
PRINT_LOCK = threading.Lock()
WEB_SOCKET = None
LIST_OF_PEERS: dict = {}

CMD_SEND_FILE = 'thisisacommandtocore_/!_sendafile'
CMD_RECV_FILE = b'thisisacommandtocore_/!_recvafile'
CMD_CLOSING_HEADER = b'thisisacommandtocore_/!_closeconnection'
CMD_FILESOCKET_HANDSHAKE = 'thisisacommandtocore_/!_filesocketopen'
FILESEND_INTITATE_HEADER = 'inititatefilesequence'
TEXT_SUCCESS_HEADER = b'textstringrecvsuccess'
CMD_FILESOCKET_CLOSE = 'thisisacommandtocore_/!_closefilesocket'
SERVER_OK = 'connectionaccepted'
REQ_FOR_LIST = b'thisisarequestocore_/!_listofusers'
HANDLE_MESSAGE_HEADER = 'thisisamessage'
HANDLE_END = 'endprogram'
HANDLE_COMMAND = 'thisisacommand'
HANDLE_FILE_HEADER = 'thisisafile'
HANDLE_CONNECT_USER = 'connectuser'
CMD_NOTIFY_USER = 'thisisacommandtocore_/!_notifyuser'


def get_ip() -> str:
    """Retrieves the local IP address of the machine.

    Attempts to connect to a public DNS server (8.8.8.8) to obtain the local IP.
    If unsuccessful, falls back to using gethostbyname().

    Returns:
        str: The local IP address as a string.

    Raises:
        soc.error: If a socket error occurs during connection.
    """
    config_soc = soc.socket(IP_VERSION, PROTOCOL)
    config_ip = 'localhost'
    try:
        if IP_VERSION == soc.AF_INET:
            config_PUBILC_DNS = "1.1.1.1"
            config_soc.connect((config_PUBILC_DNS, 80))
            config_ip = config_soc.getsockname()[0]
        else:
            response = requests.get('https://api64.ipify.org?format=json')
            if response.status_code == 200:
                data = response.json()
                config_ip = data['ip']
    except soc.error as e:
        config_ip = soc.gethostbyname(soc.gethostname()) if IP_VERSION == soc.AF_INET else \
            soc.getaddrinfo(soc.gethostname(), None, IP_VERSION)[0][4][0]
        error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")
    finally:
        config_soc.close()
        return config_ip


def is_port_empty(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except socket.error:
        return False


def validate_ports() -> None:
    global THIS_PORT, PAGE_PORT, REQ_PORT, FILE_PORT
    ports_list = [THIS_PORT, PAGE_PORT, REQ_PORT, FILE_PORT]
    for i in range(len(ports_list)):
        if is_port_empty(ports_list[i]):
            continue
        else:
            while not is_port_empty(ports_list[i]):
                ports_list[i] += 1
            error_log(f"Port is not empty. choosing another port: {ports_list[i]}")
    THIS_PORT, PAGE_PORT, REQ_PORT, FILE_PORT = ports_list
    return None


def clear_logs():
    with open(os.path.join(LOG_DIR, 'error.logs'), 'w') as e:
        e.write('')
    with os.path.join(LOG_DIR, 'activity.logs', 'w') as a:
        a.write('')
    with os.path.join(LOG_DIR, 'server.logs', 'w') as s:
        s.write('')
    return


def set_constants() -> bool:
    """Sets global constants from values in the configuration file and directories.

    Reads configuration values from config.ini and sets global variables accordingly.
    Also sets directory paths for logs and the webpage.

    Returns:
        bool: True if configuration values were set successfully, False otherwise.
    """
    global CONFIG_PATH, CURRENT_DIR, LOG_DIR, PAGE_PATH, DOWNLOAD_PATH
    CURRENT_DIR = os.path.join(os.getcwd())
    # CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_PATH = os.path.join(CURRENT_DIR, 'avails', 'config.ini')
    LOG_DIR = os.path.join(CURRENT_DIR, 'logs')
    PAGE_PATH = os.path.join(CURRENT_DIR, 'webpage')
    DOWNLOAD_PATH = os.path.join(CURRENT_DIR, 'downloads')
    # clear_logs()
    config_map = configparser.ConfigParser()
    config_map.read('avails\\config.ini')
    # print(config_map.sections())
    global USERNAME, SERVER_IP
    USERNAME = config_map["CONFIGURATIONS"]['username']
    SERVER_IP = config_map['CONFIGURATIONS']['serverip']

    global THIS_PORT, PAGE_PORT, SERVER_PORT, REQ_PORT, FILE_PORT
    SERVER_PORT = int(config_map['CONFIGURATIONS']['server_port'])
    THIS_PORT = int(config_map['NERD_OPTIONS']['this_port'])
    PAGE_PORT = int(config_map['NERD_OPTIONS']['page_port'])
    REQ_PORT = int(config_map['NERD_OPTIONS']['req_port'])
    FILE_PORT = int(config_map['NERD_OPTIONS']['file_port'])
    validate_ports()
    time.sleep(0.1)
    global PROTOCOL, IP_VERSION, THIS_IP
    PROTOCOL = socket.SOCK_STREAM if config_map['NERD_OPTIONS']['protocol'] == 'tcp' else socket.SOCK_DGRAM
    IP_VERSION = socket.AF_INET6 if config_map['NERD_OPTIONS']['ip_version'] == '6' else socket.AF_INET
    THIS_IP = get_ip()
    line_format = "{:<15} {:<10}"
    with PRINT_LOCK:
        print(':configuration choices=========================')
        time.sleep(anim_delay)
        print(line_format.format("USERNAME   :", USERNAME))
        time.sleep(anim_delay)
        print(line_format.format("YOUR IP    :", THIS_IP))
        print(line_format.format("THIS_PORT  :", THIS_PORT))
        time.sleep(anim_delay)
        print(line_format.format("SERVER_IP  :", SERVER_IP))
        time.sleep(anim_delay)
        print(line_format.format("SERVER_PORT:", SERVER_PORT))
        time.sleep(anim_delay)
        print(line_format.format("PAGE_PORT  :", PAGE_PORT))
        time.sleep(anim_delay)
        print(line_format.format("PROTOCOL   :", PROTOCOL))
        time.sleep(anim_delay)
        print(line_format.format("IP_VERSION :", IP_VERSION))
        time.sleep(anim_delay)
        print(line_format.format("REQ_PORT   :", REQ_PORT))
        time.sleep(anim_delay)
        print("===============================================")

    if USERNAME == '' or SERVER_IP == '' or THIS_PORT == 0 or PAGE_PORT == 0 or SERVER_PORT == 0:
        error_log(f"Error reading config.ini from set_constants() at line 75 in core/constants.py")
        return False

    return True
