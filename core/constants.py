import socket
import socket as soc
import threading
import configparser
import requests

from logs import *

USERNAME = ''
THISPORT = 0
PAGEPORT = 0
SERVERPORT = 0
SERVERIP = ''
FILEPORT = 45210
REQPORT = 35896

CURRENTDIR = ''
LOGDIR = ''
CONFIGPATH = ''
PAGEPATH = ''
DOWNLOADIR = ''
THISIP = ''
FORMAT = 'utf-8'
IPVERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM

MAXCALLBACKS = 6
OBJ = None
OBJTHREAD = None
REMOTEOBJECT = None
ACTIVEPEERS = []
HANDLECALL = threading.Event()
SAFELOCKFORPAGE = False
WEBSOCKET = None

CMDSENDFILE = 'thisisacommandtocore_/!_sendafile'
CMDRECVFILE = 'thisisacommandtocore_/!_recvafile'
CMDCLOSINGHEADER = 'thisisacommandtocore_/!_closeconnection'
CMDFILESOCKETHANDSHAKE = 'thisisacommandtocore_/!_filesocketopen'
FILESENDINTITATEHEADER = 'inititatefilesequence'
TEXTSUCCESSHEADER = b'textstringrecvsuccess'
CMDFILESOCKETCLOSE = 'thisisacommandtocore_/!_closefilesocket'
SERVEROK = 'connectionaccepted'
REQFORLIST = 'thisisarequestocore_/!_listofusers'


def get_ip() -> str:
    """Retrieves the local IP address of the machine.

    Attempts to connect to a public DNS server (8.8.8.8) to obtain the local IP.
    If unsuccessful, falls back to using gethostbyname().

    Returns:
        str: The local IP address as a string.

    Raises:
        soc.error: If a socket error occurs during connection.
    """
    config_soc = soc.socket(IPVERSION, PROTOCOL)
    config_ip = 'localhost'
    try:
        if IPVERSION == soc.AF_INET:
            config_PUBILC_DNS = "1.1.1.1"
            config_soc.connect((config_PUBILC_DNS, 80))
            config_ip = config_soc.getsockname()[0]
        else:
            response = requests.get('https://api64.ipify.org?format=json')
            if response.status_code == 200:
                data = response.json()
                config_ip = data['ip']
    except soc.error as e:
        config_ip = soc.gethostbyname(soc.gethostname()) if IPVERSION == soc.AF_INET else soc.getaddrinfo(soc.gethostname(), None, IPVERSION)[0][4][0]
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
    global CONFIGPATH, CURRENTDIR, LOGDIR, PAGEPATH, DOWNLOADIR
    CURRENTDIR = os.path.join(os.getcwd())
    CONFIGPATH = os.path.join(CURRENTDIR, 'avails', 'config.ini')
    LOGDIR = os.path.join(CURRENTDIR, 'logs')
    PAGEPATH = os.path.join(CURRENTDIR, 'webpage')
    DOWNLOADIR = os.path.join(CURRENTDIR, 'downloads')

    config_map = configparser.ConfigParser()
    try:
        config_map.read(CONFIGPATH)
    except configparser.ParsingError as e:
        print('::got parsing error:',e)
        return False

    global USERNAME, SERVERIP
    USERNAME = config_map['CONFIGURATIONS']['username']
    SERVERIP = config_map['CONFIGURATIONS']['serverip']

    global THISPORT,PAGEPORT,SERVERPORT,REQPORT,FILEPORT
    SERVERPORT = int(config_map['CONFIGURATIONS']['serverport'])
    THISPORT = int(config_map['NERDOPTIONS']['thisport'])
    PAGEPORT = int(config_map['NERDOPTIONS']['pageport'])
    REQPORT = int(config_map['NERDOPTIONS']['reqport'])
    FILEPORT = int(config_map['NERDOPTIONS']['fileport'])

    global PROTOCOL, IPVERSION, THISIP
    PROTOCOL = socket.SOCK_STREAM if config_map['NERDOPTIONS']['protocol'] == 'tcp' else socket.SOCK_DGRAM
    IPVERSION = socket.AF_INET6 if config_map['NERDOPTIONS']['ipversion'] == '6' else socket.AF_INET
    print('::configuration choices : ',USERNAME,':',THISPORT, SERVERIP,':',SERVERPORT,PAGEPORT,config_map['NERDOPTIONS']['protocol'], config_map['NERDOPTIONS']['ipversion'])
    THISIP = get_ip()

    if USERNAME == '' or SERVERIP == '' or THISPORT == 0 or PAGEPORT == 0 or SERVERPORT == 0:
        errorlog(f"Error reading config.ini from set_constants() at line 75 in core/constants.py")
        return False

    return True
