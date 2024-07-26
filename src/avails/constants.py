import socket as soc
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


PORT_THIS = 9000
PORT_SERVER = 9001
PORT_REQ = 9002
PORT_PAGE = 12260
PORT_FILE = 45210
PORT_PAGE_SERVE = 40000

PATH_CURRENT = '../..'
PATH_LOG = '../../logs'
PATH_PROFILES = '../../profiles'
PATH_PAGE = '../webpage'
PATH_DOWNLOAD = path.join(path.expanduser('~'), 'Downloads')
PATH_CONFIG = f'..\\configurations\\{DEFAULT_CONFIG_FILE}'

IP_VERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM
LOCK_PRINT = Lock()

MAX_CALL_BACKS = 5
MAX_RETIRES = 7


CMD_RECV_FILE_AGAIN = 'this is command to core_/!_recv file again'
CMD_RECV_FILE = 'this is a command to core_/!_recv a file'
CMD_CLOSING_HEADER = 'this is a command to core_/!_close connection'
CMD_TEXT = "this is a message"
CMD_RECV_DIR = 'this is a command to core_/!_recv dir'


CMD_VERIFY_HEADER = b'this is a verification header'
VERIFY_OK = b'verification okay'
CMD_FILESOCKET_HANDSHAKE = b'this is a command to core_/!_file socket open'
CMD_FILE_SUCCESS = b'file_success'
TEXT_SUCCESS_HEADER = b'str recv success'

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
