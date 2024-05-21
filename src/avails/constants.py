import socket as soc
import threading
import platform


CLEAR_LOGS = 1
END_OR_NOT = False
USERNAME = 'admin'
SERVER_IP = ''
THIS_IP = 'localhost'

SYS_NAME = platform.system()
WINDOWS = bool(SYS_NAME == "Windows")
DARWIN = bool(SYS_NAME == "Darwin")
LINUX = bool(SYS_NAME == "Linux")

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

PATH_CURRENT = ''
PATH_LOG = ''
PATH_PROFILES = ''
PATH_PAGE = ''
PATH_DOWNLOAD = ''


IP_VERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM
count_of_user_id = 0
LOCK_USER_ID = threading.Lock()
LOCK_PRINT = threading.Lock()
LOCK_LIST_PEERS = threading.Lock()


ACTIVE_PEERS = []
PROFILE_LIST = []
CONTROL_FLAG = [threading.Event() for x in range(10)]
for event in CONTROL_FLAG:
    event.set()

# This list has the whole control over the project files where functions
# block for resources until they get themselves available
# almost every while loop checks for their respective event's `threading.Event::is_set` function
# to proceed further or not
# and as the door,s open for exceptions some part of program may use their object's event to check for
# end() functions available in this program mostly set their respective events
# which lead to blocking parts break.

# Respective indexes are named for readability
# PEER_TEXT = 0
# NOMAD_FLAG = 1
# REQ_FLAG = 2
# _ = 3 # use !!
# USE ABLES_FLAG = 4
# CONNECT_SERVER_FLAG = 5

# and
# the suggestion to use a non-blocking socket instead of
# while event.is_set():
#    readable,_,_ = select.select([socket.socket],[],[],_timeout=0.00x)
#    if socket.socket in readable:
#       break
# hMM... can be suppressed (it's tested :)

LIST_OF_PEERS: dict = {}

anim_delay = 0.07
MAX_CALL_BACKS = 5
REQ_URI_CONNECT = 12
BASIC_URI_CONNECTOR = 13


HOST_OBJ = None
OBJ_THREAD = None
REQUESTS_THREAD = None
THIS_OBJECT = None
SERVER_THREAD = None
PAGE_HANDLE_CALL = threading.Event()
HOLD_PROFILE_SETUP = threading.Event()
WEB_SOCKET = None


CMD_RECV_FILE = 'this is a command to core_/!_recv a file'
CMD_CLOSING_HEADER = 'this is a command to core_/!_close connection'
CMD_FILESOCKET_HANDSHAKE = 'this is a command to core_/!_file socket open'
CMD_TEXT = "this is a message"
CMD_RECV_DIR = 'this is a command to core_/!_recv dir'
CMD_RECV_DIR_LITE = b'this is a command to core_/!_recv dir_lite'


CMD_FILE_SUCCESS = b'file_success'
TEXT_SUCCESS_HEADER = b'text string recv success'
REQ_FOR_LIST = b'this is a request to core_/!_list of users'
I_AM_ACTIVE = b'this is a command to core_/!_notify user'
SERVER_PING = b'this is a command from server_/!_ping'
SOCKET_OK = b"socket_ok"


SERVER_OK = 'connection accepted'
LIST_SYNC = 'sync list'
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
ACTIVE_PING = b"why_s ur face like that"
