import socket
import webbrowser
import configparser
import socket as soc
import subprocess
import urllib.request
import ipaddress

from src.avails import useables as use
from src.core import *
from src.configurations.configure_app import set_constants


def initiate():
    clear_logs() if const.CLEAR_LOGS else None
    config_map = configparser.ConfigParser()
    try:
        config_map.read(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE))
    except KeyError:
        write_default_configurations()
        config_map.read(os.path.join(const.PATH_PROFILES, const.DEFAULT_CONFIG_FILE))
    set_constants(config_map)
    const.THIS_IP = get_ip()
    const.IP_VERSION = socket.AF_INET6 if ipaddress.ip_address(const.THIS_IP).version == 6 else socket.AF_INET
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
        return get_v4() or 'localhost'
    elif const.IP_VERSION == soc.AF_INET6:
        if soc.has_ipv6:
            return get_v6() or get_v4() or '::1'
        else:
            return get_ip()


def get_v4():
    with soc.socket(soc.AF_INET, soc.SOCK_DGRAM) as config_soc:
        try:
            config_soc.connect(('1.1.1.1', 80))
            config_ip = config_soc.getsockname()[0]
        except soc.error as e:
            error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")

            config_ip = soc.gethostbyname(soc.gethostname())
            if const.DARWIN or const.LINUX:
                config_ip = subprocess.getoutput("hostname -I")

    return config_ip


"""
    import commands
    ips = commands.getoutput("/sbin/ifconfig | grep -i \"inet\" | grep -iv \"inet6\" | " +
                         "awk {'print $2'} | sed -ne 's/addr: / /p'")
    print ips
"""


def get_v6():
    if const.WINDOWS:
        local_v6 = ""
        for sock_tuple in soc.getaddrinfo("", None, soc.AF_INET6, proto=const.PROTOCOL, flags=soc.AI_PASSIVE):
            ip, _, _, _ = sock_tuple[4]
            if not ipaddress.ip_address(ip).is_link_local:
                return ip
    elif const.DARWIN or const.LINUX:
        return get_v6_from_shell() or get_v6_from_api64()


def get_v6_from_shell():
    try:
        import subprocess

        result = subprocess.run(['ip', '-6', 'addr', 'show'], capture_output=True, text=True)
        output_lines = result.stdout.split('\n')

        ip_v6 = []
        for line in output_lines:
            if 'inet6' in line and 'fe80' not in line and '::1' not in line:
                ip_v6.append(line.split()[1])
    except Exception as exp:
        print(f"Error occurred: {exp}")
        return []
    return ip_v6[0]


def get_v6_from_api64():
    config_ip = "::1"  # Default IPv6 address

    try:
        with urllib.request.urlopen('https://api64.ipify.org?format=json') as response:
            data = response.read().decode('utf-8')
            data_dict = json.loads(data)
            config_ip = data_dict.get('ip', config_ip)
    except (urllib.request.HTTPError, json.JSONDecodeError) as e:
        error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")
        config_ip = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6)[0][4][0]

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
        'page_port_signals = 42057'
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
    except socket.gaierror:
        print("ERROR IN SETTING UP NETWORK ")
        exit(1)
    except (OSError,socket.error):
        return False


def validate_ports() -> None:
    ports_list = [const.PORT_THIS, const.PORT_PAGE_DATA, const.PORT_PAGE_SIGNALS, const.PORT_REQ,
                  const.PORT_FILE]
    for i, port in enumerate(ports_list):
        if is_port_empty(port):
            continue
        else:
            while not is_port_empty(port):
                port += 1
                time.sleep(1)
            ports_list[i] += port
            error_log(f"Port is not empty. choosing another port: {ports_list[i]}")
    const.PORT_THIS, const.PORT_PAGE_DATA, const.PORT_PAGE_SIGNALS, const.PORT_REQ, const.PORT_FILE = ports_list
    return None


@NotInUse
def retrace_browser_path():
    if const.WINDOWS:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice")
        prog_id, _ = winreg.QueryValueEx(key, 'ProgId')
        key.Close()

        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"\\{prog_id}\shell\open\command")
        path, _ = winreg.QueryValueEx(key, '')
        key.Close()

        return path.strip('"')

    if const.DARWIN:
        return subprocess.check_output(["osascript",
                                        "-e",
                                        'tell application "System Events" to get POSIX path of (file of process "Safari" as alias)'
                                        ]).decode().strip()

    if const.LINUX:
        command_output = subprocess.check_output(["xdg-settings", "get", "default-web-browser"]).decode().strip()

        if command_output.startswith('userapp-'):
            command_output = subprocess.check_output(["xdg-mime", "query", "default", "text/html"]).decode().strip()

        return command_output


def launch_web_page():
    page_url = os.path.join(const.PATH_PAGE, "index.html")
    try:
        webbrowser.open(page_url)
    except webbrowser.Error:
        if const.WINDOWS:
            os.system(f"start {page_url}")

        elif const.LINUX or const.DARWIN:
            subprocess.Popen(['xdg-open', page_url])

        pass
    except FileNotFoundError:
        use.echo_print("::webpage not found, look's like the package you downloaded is corrupted")
