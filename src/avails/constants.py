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
MAX_DATAGRAM_SIZE = 1024 * 256
GLOBAL_TTL_FOR_GOSSIP = 6
NODE_POV_GOSSIP_TTL = 3
PERIODIC_TIMEOUT_TO_ADD_THIS_REMOTE_PEER_TO_LISTS = 7

VERSIONS = {
    'GLOBAL': 1.1,
    'RP': 1.0,
    'FO': 1.0,
    'DO': 1.0,
    'WIRE':1.0,
}

CMD_RECV_FILE_AGAIN = b'recv file again '
CMD_RECV_FILE = b'receive file    '
CMD_CLOSING_HEADER = b'close connection'
CMD_TEXT = b'this is message '
CMD_RECV_DIR = b'cmd to recv dir '

CMD_VERIFY_HEADER = b'verify header   '
VERIFY_OK = b'verify okay     '
CMD_FILESOCKET_HANDSHAKE = b'file sock open  '
CMD_FILE_SUCCESS = b'file_success    '
TEXT_SUCCESS_HEADER = b'str success     '

REQ_FOR_LIST = b'list of users  '
I_AM_ACTIVE = b'com notify user'
SERVER_PING = b' server_/!_ping'
SOCKET_OK = b'socket_ok      '

SERVER_OK = b'connect accepted'
REDIRECT = b'redirect        '
LIST_SYNC = b'sync list       '
ACTIVE_PING = b"face like that  "
HANDLE_MESSAGE_HEADER = 'this is  message'
HANDLE_END = 'end program     '
HANDLE_COMMAND = 'this is command '
HANDLE_FILE_HEADER = 'this is file    '
HANDLE_CONNECT_USER = 'connect user    '
HANDLE_RELOAD = 'this is reload  '
HANDLE_DIR_HEADER = 'this is a dir   '
HANDLE_POP_DIR_SELECTOR = 'pop dir selector'
HANDLE_OPEN_FILE = 'open file       '
HANDLE_SYNC_USERS = 'sync users      '
HANDLE_VERIFICATION = 'han verification'
