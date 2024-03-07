import socket as soc
import threading

CLEARLOGSFLAG = 1

USERNAME = ''
SERVER_IP = ''
THIS_IP = ''
SERVER_TIMEOUT = 5

PORT_THIS = 0
PORT_PAGE = 0
PORT_SERVER = 0
PORT_FILE = 45210
PORT_REQ = 35896
PORT_PAGE_SERVE = 40000

PATH_CURRENT = ''
PATH_LOG = ''
PATH_CONFIG = ''
PATH_PAGE = ''
PATH_DOWNLOAD = ''

IP_VERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM
FORMAT = 'utf-8'
count_of_user_id = 0
LOCK_USER_ID = threading.Lock()
LOCK_PRINT = threading.Lock()
LOCK_LIST_PEERS = threading.Lock()
LOCK_FOR_PAGE = False
ACTIVE_PEERS = []
LIST_OF_PEERS: dict = {}
anim_delay = 0.1
MAX_CALL_BACKS = 6

OBJ = None
OBJ_THREAD = None
REQUESTS_THREAD = None
THIS_OBJECT= None
SERVER_THREAD = None
PAGE_HANDLE_CALL = threading.Event()
WEB_SOCKET = None

CMD_RECV_FILE = 'thisisacommandtocore_/!_recvafile'
CMD_CLOSING_HEADER = 'thisisacommandtocore_/!_closeconnection'
CMD_FILESOCKET_HANDSHAKE = 'thisisacommandtocore_/!_filesocketopen'
CMD_TEXT = "thisisamessage"
CMD_RECV_DIR = 'thisisacommandtocore_/!_recvdir'
CMD_RECV_DIR_LITE = b'thisisacommandtocore_/!_recvdir_lite'

TEXT_SUCCESS_HEADER = b'textstringrecvsuccess'
REQ_FOR_LIST = b'thisisarequestocore_/!_listofusers'
I_AM_ACTIVE = b'thisisacommandtocore_/!_notifyuser'
SERVER_PING = b'thisisacommandfromserver_/!_ping'

SERVER_OK = 'connectionaccepted'
LIST_SYNC = 'synclist'
HANDLE_MESSAGE_HEADER = 'thisisamessage'
HANDLE_END = 'endprogram'
HANDLE_COMMAND = 'thisisacommand'
HANDLE_FILE_HEADER = 'thisisafile'
HANDLE_CONNECT_USER = 'connectuser'
HANDLE_RELOAD = 'thisiscommandtocore_/!_reload'
HANDLE_DIR_HEADER = 'thisisadir'
HANDLE_POP_DIR_SELECTOR = 'popdirselector'
HANDLE_PUSH_FILE_SELECTOR = 'pushfileselector'
HANDLE_OPEN_FILE = 'openfile'
HANDLE_DIR_HEADER_LITE = 'thisisadirlite'
HANDLE_SYNC_USERS = 'syncusers'
ACTIVE_PING = b"why_s ur facelikethat"
# ACTIVE_PONG = b"my face_s like that only what??"
