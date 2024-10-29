import socket
from sys import platform
from os import path
from threading import Lock


CLEAR_LOGS = 1
USERNAME = 'admin'
SERVER_IP = '127.0.0.1'
THIS_IP = '127.0.0.1'

WINDOWS = platform == "win32"
DARWIN = platform == "darwin"
LINUX = platform == "linux"

SERVER_TIMEOUT = 6
DEFAULT_CONFIG_FILE = 'default_config.ini'
FORMAT = 'utf-8'

PORT_THIS = 12000
PORT_SERVER = 12001
PORT_REQ = 12002
PORT_NETWORK = 12003
PORT_PAGE = 12260
PORT_FILE = 45210
PORT_PAGE_SERVE = 40000

PATH_CURRENT = '../..'
PATH_LOG = '../../logs'
PATH_PROFILES = '../../profiles'
PATH_PAGE = '../webpage'
PATH_DOWNLOAD = path.join(path.expanduser('~'), 'Downloads')
PATH_CONFIG = f'..\\configurations\\{DEFAULT_CONFIG_FILE}'

IP_VERSION = socket.AF_INET
FILE_ERROR_EXT = '.pc-unconfirmedownload'
debug = False

if debug:
    from src.avails.connect import TCPProtocol
    PROTOCOL = TCPProtocol
else:
    PROTOCOL = None
LOCK_PRINT = Lock()

MAX_LOAD = 5
MAX_CALL_BACKS = 5
MAX_RETIRES = 7
MAX_DATAGRAM_RECV_SIZE = 1024 * 256  # 256 KB
MAX_DATAGRAM_SEND_SIZE = 1024 * 63  # 63 KB
# MAX_OTM_BUFFERING = 1024 * 1024 * 10  # 10 MB
MAX_OTM_BUFFERING = 20  # 20 chunks

GLOBAL_TTL_FOR_GOSSIP = 6
NODE_POV_GOSSIP_TTL = 3
DEFAULT_GOSSIP_FANOUT = 5
PERIODIC_TIMEOUT_TO_ADD_THIS_REMOTE_PEER_TO_LISTS = 7

VERSIONS = {
    'GLOBAL': 1.1,
    'RP': 1.0,
    'FO': 1.0,
    'DO': 1.0,
    'WIRE':1.0,
}