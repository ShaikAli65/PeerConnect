import socket
from os import path
from sys import platform
from threading import Lock
from typing import Optional, TYPE_CHECKING

CLEAR_LOGS = 1
USERNAME = "admin"
SERVER_IP = "127.0.0.1"

THIS_IP = None

if TYPE_CHECKING:
    from src.avails import connect
    THIS_IP: connect.IPAddress

MULTICAST_IP_v4 = "239.1.11.11"
MULTICAST_IP_v6 = "ff02::1:6"
BROADCAST_IP = "255.255.255.255"
_BIND_IP_V4 = "0.0.0.0"
_BIND_IP_V6 = "::"
BIND_IP = _BIND_IP_V4
WEBSOCKET_BIND_IP = "localhost"

IS_WINDOWS = platform == "win32"
IS_DARWIN = platform == "darwin"
IS_LINUX = platform == "linux"

SERVER_TIMEOUT = 6
DEFAULT_CONFIG_FILE = "default_config.ini"
DEFAULT_PROFILE_NAME = "default_profile.ini"

FORMAT = "utf-8"

DATA = 0x00
SIGNAL = 0x01

PORT_THIS = 3485
PORT_REQ = 3486
PORT_NETWORK = PORT_REQ
PORT_SERVER = 3487
PORT_PAGE = 12260
PORT_PAGE_SERVE = 40000

PATH_CURRENT = "../.."
PATH_LOG = "../../logs"
PATH_PROFILES = "../../profiles"
PATH_PAGE = "../webpage"
PATH_DOWNLOAD = path.join(path.expanduser("~"), "Downloads")
PATH_CONFIG = f"..\\configurations\\{DEFAULT_CONFIG_FILE}"
PATH_LOG_CONFIG = "..\\configurations\\log_config.json"

IP_VERSION = socket.AF_INET6
USING_IP_V4 = True
USING_IP_V6 = False

FILE_ERROR_EXT = ".pc-unconfirmedownload"
debug = False

PROTOCOL = None

if TYPE_CHECKING:
    from src.avails.connect import TCPProtocol

    PROTOCOL: Optional[TCPProtocol]

LOCK_PRINT = Lock()

MAX_LOAD = 5
MAX_CALL_BACKS = 5
MAX_RETIRES = 7
MAX_DATAGRAM_RECV_SIZE = 1024 * 256  # 256 KB
MAX_DATAGRAM_SEND_SIZE = 1024 * 63  # 63 KB
MAX_OTM_BUFFERING = 20  # 20 chunks
MAX_CONNECTIONS_BETWEEN_PEERS = 6
MAX_TOTAL_CONNECTIONS = 40
MAX_FRONTEND_MESSAGE_BUFFER_LEN = 1000
MAX_CONCURRENT_MSG_PROCESSING = 6

GLOBAL_TTL_FOR_GOSSIP = 6
NODE_POV_GOSSIP_TTL = 3
DEFAULT_GOSSIP_FANOUT = 5
TRANSFER_STATUS_UPDATE_FREQ = 10

PERIODIC_TIMEOUT_TO_ADD_THIS_REMOTE_PEER_TO_LISTS = 7
DEFAULT_TRANSFER_TIMEOUT = 4
PING_TIMEOUT = 4
PALM_TREE_LINK_TIMEOUT = 3
DISCOVER_TIMEOUT = 3
TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK = 4


VERSIONS = {
    "GLOBAL": 1.1,
    "RP": 1.0,
    "FO": 1.0,
    "DO": 1.0,
    "WIRE": 1.0,
}

DISCOVER_RETRIES = 2
PING_TIME_CHECK_WINDOW = 3.0

BYTES_PER_KB = 1024.0
RATE_WINDOW = .0001
