import webbrowser

from src.avails import useables as use
from src.core import *
from src.configurations.configure_app import set_constants
import configparser
import requests
import socket as soc
import subprocess


def initiate():
    const.THIS_IP = get_ip()
    clear_logs() if const.CLEARLOGSFLAG else None
    config_map = configparser.ConfigParser()
    try:
        config_map.read(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE))
    except KeyError:
        write_default_configurations()
        config_map.read(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE))
    set_constants(config_map)
    validate_ports()


def get_ip() -> str:
    """Retrieves the local IP address of the machine.

    Attempts to connect to a public DNS server (1.1.1.1) to obtain the local IP.
    If unsuccessful, falls back to using gethostbyname().

    Returns:
        str: The local IP address as a string.

    Raises:
        soc.error: If a socket error occurs during connection.
    """
    if const.IP_VERSION == soc.AF_INET:
        config_ip = get_v4()
    else:
        config_ip = get_v6()
    return config_ip


def get_v4():
    with soc.socket(const.IP_VERSION, soc.SOCK_DGRAM) as config_soc:
        config_soc.settimeout(3)
        try:
            config_soc.connect(('1.1.1.1', 80))
            config_ip, _ = config_soc.getsockname()
        except soc.error as e:
            error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")

            config_ip = soc.gethostbyname(soc.gethostname())
            if const.SYS_NAME == const.DARWIN or const.SYS_NAME == const.LINUX:
                config_ip = subprocess.getoutput("hostname -I")

    return config_ip


"""
    import commands
    ips = commands.getoutput("/sbin/ifconfig | grep -i \"inet\" | grep -iv \"inet6\" | " +
                         "awk {'print $2'} | sed -ne 's/addr: / /p'")
    print ips
"""


def get_v6():
    config_ip = "::1"
    try:
        response = requests.get('https://api64.ipify.org?format=json')
        if response.status_code == 200:
            data = response.json()
            config_ip = data['ip']
    except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
        error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")
        config_ip = soc.getaddrinfo(soc.gethostname(), None, const.IP_VERSION)[0][4][0]
    return config_ip


def set_paths():
    const.PATH_CURRENT = os.path.join(os.getcwd())
    const.PATH_PROFILES = os.path.join(const.PATH_CURRENT, 'profiles')
    const.PATH_LOG = os.path.join(const.PATH_CURRENT, 'logs')
    const.PATH_PAGE = os.path.join(const.PATH_CURRENT, 'src', 'webpage')
    downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
    # check if the directory exists
    if not os.path.exists(downloads_path):
        downloads_path = os.path.join(os.path.expanduser('~'), 'Desktop')

    const.PATH_DOWNLOAD = os.path.join(downloads_path, 'PeerConnect')
    try:
        os.makedirs(const.PATH_DOWNLOAD, exist_ok=True)
    except OSError as e:
        error_log(f"Error creating directory: {e} from set_paths() at line 70 in core/constants.py")


def clear_logs():
    with open(os.path.join(const.PATH_LOG, 'error.logs'), 'w') as e:
        e.write('')
    with open(os.path.join(const.PATH_LOG, 'activity.logs'), 'w') as a:
        a.write('')
    with open(os.path.join(const.PATH_LOG, 'server.logs'), 'w') as s:
        s.write('')


def write_default_configurations():
    default_config_file = (
        '[NERD_OPTIONS]'
        'this_port = 48221'
        'page_port = 12260'
        'ip_version = 4'
        'protocol = tcp'
        'req_port = 35623'
        'file_port = 35621'
        'page_serve_port = 40000'
        '\n'
        '[USER_PROFILES]'
        'admin = admin.ini'
    )
    default_profile_file = (
        '[CONFIGURATIONS]'
        'username = admin'
        'server_port = 45000'
        'serverip = 0.0.0.0'
    )

    with open(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE), 'w+') as config_file:
        config_file.write(default_config_file)
    with open(os.path.join(const.PATH_PROFILES, 'admin.ini'), 'w+') as profile_file:
        profile_file.write(default_profile_file)


def is_port_empty(port):
    try:
        with soc.socket(const.IP_VERSION, soc.SOCK_STREAM) as s:
            s.bind((const.THIS_IP, port))
            return True
    except OSError:
        return False


def validate_ports() -> None:
    ports_list = [const.PORT_THIS, const.PORT_PAGE_DATA, const.PORT_PAGE_SIGNALS, const.PORT_REQ,
                  const.PORT_FILE]
    for i in range(len(ports_list)):
        if is_port_empty(ports_list[i]):
            continue
        else:
            while not is_port_empty(ports_list[i]):
                ports_list[i] += 1
            error_log(f"Port is not empty. choosing another port: {ports_list[i]}")
    const.PORT_THIS, const.PORT_PAGE_DATA, const.PORT_PAGE_SIGNALS, const.PORT_REQ, const.PORT_FILE = ports_list
    return None


@NotInUse
def retrace_browser_path():
    if const.SYS_NAME == const.WINDOWS:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice")
        prog_id, _ = winreg.QueryValueEx(key, 'ProgId')
        key.Close()

        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"\\{prog_id}\shell\open\command")
        path, _ = winreg.QueryValueEx(key, '')
        key.Close()

        return path.strip('"')

    if const.SYS_NAME == const.DARWIN:
        return subprocess.check_output(["osascript",
                                        "-e",
                                        'tell application "System Events" to get POSIX path of (file of process "Safari" as alias)'
                                        ]).decode().strip()

    if const.SYS_NAME == const.LINUX:
        command_output = subprocess.check_output(["xdg-settings", "get", "default-web-browser"]).decode().strip()

        if command_output.startswith('userapp-'):
            command_output = subprocess.check_output(["xdg-mime", "query", "default", "text/html"]).decode().strip()

        return command_output


def launch_web_page():
    page_url = os.path.join(const.PATH_PAGE, "index.html")
    try:
        webbrowser.open(page_url)
    except webbrowser.Error:
        if const.SYS_NAME == const.WINDOWS:
            os.system(f"start {page_url}")

        elif const.SYS_NAME == const.LINUX or const.SYS_NAME == const.DARWIN:
            subprocess.Popen(['xdg-open', page_url])

        pass
    except FileNotFoundError:
        use.echo_print(False,"::webpage not found, look's like the package you downloaded is corrupted")
