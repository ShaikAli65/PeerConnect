import socket as soc
import threading
from sys import platform

from os import path

from src.avails.container import PeerDict

CLEAR_LOGS = 1
END_OR_NOT = False
USERNAME = 'admin'
SERVER_IP = ''
THIS_IP = 'localhost'

WINDOWS = platform == "win32"
DARWIN = platform == "darwin"
LINUX = platform == "linux"

SERVER_TIMEOUT = 6
DEFAULT_CONFIG_FILE = 'default_config.ini'
FORMAT = 'utf-8'


PORT_THIS = 0
PORT_PAGE_SIGNALS = 42057
PORT_PAGE_DATA = 12260
PORT_SERVER = 0
PORT_FILE = 45210
PORT_REQ = 35896
PORT_PAGE_SERVE = 40000

PATH_CURRENT = '..\\..'
PATH_LOG = '..\\..\\logs'
PATH_PROFILES = '..\\..\\profiles'
PATH_PAGE = '..\\webpage'
PATH_DOWNLOAD = path.join(path.expanduser('~'), 'Downloads')


IP_VERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM
LOCK_PRINT = threading.Lock()
LOCK_LIST_PEERS = threading.Lock()


ACTIVE_PEERS = []
PROFILE_LIST = []

FLAGZ = [threading.Event() for x in range(10)]


# This list has the whole control over the project files where functions
# block for resources until they get themselves available
# almost every while loop checks for their respective event's `threading.Event::is_set` function
# to proceed further or not
# and as the door,s open for exceptions some part of program may use their object's event to check for
# end() functions available in this program mostly flip their respective events
# which leads to blocking parts break.

# Respective Events are named for readability
PEER_TEXT_FLAG = FLAGZ[0]
NOMAD_FLAG = FLAGZ[1]
REQ_FLAG = FLAGZ[2]
RP_FLAG = FLAGZ[3]
USEABLES_FLAG = FLAGZ[4]
CONNECT_SERVER_FLAG = FLAGZ[5]
DATA_WEAVER_FLAG = FLAGZ[6]
LIST_OF_PEERS = PeerDict()

MAX_CALL_BACKS = 5

HOST_OBJ = None
OBJ_THREAD = None
REQUESTS_THREAD = None
THIS_OBJECT = None
SERVER_THREAD = None
PAGE_HANDLE_CALL = threading.Event()
HOLD_PROFILE_SETUP = threading.Event()
WEB_SOCKET = None


CMD_RECV_FILE_AGAIN = 'this is command to core_/!_recv file again'
CMD_RECV_FILE = 'this is a command to core_/!_recv a file'
CMD_CLOSING_HEADER = 'this is a command to core_/!_close connection'
CMD_TEXT = "this is a message"
CMD_RECV_DIR = 'this is a command to core_/!_recv dir'


CMD_VERIFY_HEADER = b'this is a verification header'
VERIFY_OK = b'verification okay'
CMD_FILESOCKET_HANDSHAKE = b'this is a command to core_/!_file socket open'
CMD_FILE_SUCCESS = b'file_success'
TEXT_SUCCESS_HEADER = b'text string recv success'
REQ_FOR_LIST = b'this is a request to core_/!_list of users'
I_AM_ACTIVE = b'this is a command to core_/!_notify user'
SERVER_PING = b'this is a command from server_/!_ping'
SOCKET_OK = b"socket_ok"


SERVER_OK = b'connection accepted'
REDIRECT = b'redirect'
LIST_SYNC = b'sync list'
ACTIVE_PING = b"why_s ur face like that"

HANDLE_MESSAGE_HEADER = 'this is a message'
HANDLE_END = 'end program'
HANDLE_COMMAND = 'this is a command'
HANDLE_FILE_HEADER = 'this is a file'
HANDLE_CONNECT_USER = 'connect user'
HANDLE_RELOAD = 'this is command to core_/!_reload'
HANDLE_DIR_HEADER = 'this is a dir'
HANDLE_POP_DIR_SELECTOR = 'pop dir selector'
HANDLE_PUSH_FILE_SELECTOR = 'push file selector'
HANDLE_OPEN_FILE = 'open file'
HANDLE_SYNC_USERS = 'sync users'
HANDLE_VERIFICATION = 'handle verification'
