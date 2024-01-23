import socket
import socket as soc
import threading
import configparser
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
DOWNLOADIR = ''
THIS_IP = ''
FORMAT = 'utf-8'
IP_VERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM

MAX_CALL_BACKS = 6
OBJ = None
OBJ_THREAD = None
REQUESTS_THREAD = None
REMOTE_OBJECT = None
ACTIVE_PEERS = []
HANDLE_CALL = threading.Event()
SAFE_LOCK_FOR_PAGE = False
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
REQ_FOR_LIST = 'thisisarequestocore_/!_listofusers'
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
        errorlog(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")
    finally:
        config_soc.close()
        return config_ip


def set_constants() -> bool:
    """Sets global constants from values in the configuration file and directories.

    Reads configuration values from config.ini and sets global variables accordingly.
    Also sets directory paths for logs and the webpage.

    Returns:
        bool: True if configuration values were set successfully, False otherwise.
    """
    global CONFIG_PATH, CURRENT_DIR, LOG_DIR, PAGE_PATH, DOWNLOADIR
    CURRENT_DIR = os.path.join(os.getcwd())
    CONFIG_PATH = os.path.join(CURRENT_DIR, 'avails', 'config.ini')
    LOG_DIR = os.path.join(CURRENT_DIR, 'logs')
    PAGE_PATH = os.path.join(CURRENT_DIR, 'webpage')
    DOWNLOADIR = os.path.join(CURRENT_DIR, 'downloads')

    config_map = configparser.ConfigParser()
    try:
        config_map.read(CONFIG_PATH)
    except configparser.ParsingError as e:
        print('::got parsing error:', e)
        return False

    global USERNAME, SERVER_IP
    USERNAME = config_map['CONFIGURATIONS']['username']
    SERVER_IP = config_map['CONFIGURATIONS']['serverip']

    global THIS_PORT, PAGE_PORT, SERVER_PORT, REQ_PORT, FILE_PORT
    SERVER_PORT = int(config_map['CONFIGURATIONS']['serverport'])
    THIS_PORT = int(config_map['NERDOPTIONS']['thisport'])
    PAGE_PORT = int(config_map['NERDOPTIONS']['pageport'])
    REQ_PORT = int(config_map['NERDOPTIONS']['reqport'])
    FILE_PORT = int(config_map['NERDOPTIONS']['fileport'])

    global PROTOCOL, IP_VERSION, THIS_IP
    PROTOCOL = socket.SOCK_STREAM if config_map['NERDOPTIONS']['protocol'] == 'tcp' else socket.SOCK_DGRAM
    IP_VERSION = socket.AF_INET6 if config_map['NERDOPTIONS']['ipversion'] == '6' else socket.AF_INET
    print('::configuration choices : ', USERNAME, ':', THIS_PORT, SERVER_IP, ':', SERVER_PORT, PAGE_PORT,
          config_map['NERDOPTIONS']['protocol'], config_map['NERDOPTIONS']['ipversion'])
    THIS_IP = get_ip()

    if USERNAME == '' or SERVER_IP == '' or THIS_PORT == 0 or PAGE_PORT == 0 or SERVER_PORT == 0:
        errorlog(f"Error reading config.ini from set_constants() at line 75 in core/constants.py")
        return False

    return True
