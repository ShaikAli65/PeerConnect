import socket as soc
import threading
import configparser

from logs import *

USERNAME = ''
THISPORT = 0
PAGEPORT = 0
SERVERPORT = 0
SERVERIP = ''

CURRENTDIR = ''
LOGDIR = ''
CONFIGPATH = ''
PAGEPATH = ''
THISIP = ''
FORMAT = 'utf-8'

MAXCALLBACKS = 6
OBJ = None
SERVERTHREAD = None
OBJTHREAD = None
SERVEDATA = None
ACTIVEPEERS = []
HANDLECALL = threading.Event()
SAFELOCKFORPAGE = False
WEBSOCKET = None

CMDSENDFILE = 'thisisacommandtocore_/!_recvafile'
CMDRECVFILE = 'thisisacommandtocore_/!_sendafile'
CMDCLOSINGHEADER = 'thisisacommandtocore_/!_closeconnection'.encode(FORMAT)
FILESENDINTITATEHEADER = 'inititatingfilesequence'.encode(FORMAT)
TEXTSUCCESSHEADER = 'textstringrecvsuccess'.encode(FORMAT)


def get_local_ip() -> str:
    """Retrieves the local IP address of the machine.

    Attempts to connect to a public DNS server (8.8.8.8) to obtain the local IP.
    If unsuccessful, falls back to using gethostbyname().

    Returns:
        str: The local IP address as a string.

    Raises:
        soc.error: If a socket error occurs during connection.
    """
    config_soc = soc.socket(soc.AF_INET, soc.SOCK_STREAM)
    config_ip = ''
    try:
        config_PUBILC_DNS = "1.1.1.1"
        config_soc.connect((config_PUBILC_DNS, 80))
        config_ip = config_soc.getsockname()[0]
    except soc.error as e:
        errorlog(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")
        config_ip = soc.gethostbyname(soc.gethostname())
    finally:
        print(f"Local IP: {config_ip}")
        config_soc.close()
        return config_ip


def set_constants() -> bool:
    """Sets global constants from values in the configuration file and directories.

    Reads configuration values from config.txt and sets global variables accordingly.
    Also sets directory paths for logs and the webpage.

    Returns:
        bool: True if configuration values were set successfully, False otherwise.
    """
    global CONFIGPATH, CURRENTDIR, LOGDIR, PAGEPATH
    CURRENTDIR = os.path.join(os.getcwd())
    CONFIGPATH = os.path.join(CURRENTDIR, 'avails', 'config.txt')
    LOGDIR = os.path.join(CURRENTDIR, 'logs')
    PAGEPATH = os.path.join(CURRENTDIR, 'webpage')

    global THISIP, USERNAME, THISPORT, PAGEPORT, SERVERPORT, SERVERIP
    THISIP = get_local_ip()
    config_map = configparser.ConfigParser()
    config_map.read(CONFIGPATH)
    USERNAME = config_map['CONFIGURATIONS']['username']
    SERVERIP = config_map['CONFIGURATIONS']['serverip']
    THISPORT = int(config_map['CONFIGURATIONS']['thisport'])
    PAGEPORT = int(config_map['CONFIGURATIONS']['pageport'])
    SERVERPORT = int(config_map['CONFIGURATIONS']['serverport'])
    if USERNAME == '' or SERVERIP == '' or THISPORT == 0 or PAGEPORT == 0 or SERVERPORT == 0:
        errorlog(f"Error reading config.txt from set_constants() at line 75 in core/constants.py")
        return False
    return True
