import webbrowser
import configparser
import socket as soc
import subprocess
import urllib.request
import ipaddress
import random

import src.avails.connect
from src.avails.connect import is_port_empty
from src.avails.remotepeer import RemotePeer
from src.core import *
from src.configurations.configure_app import set_constants


def initiate():
    clear_logs() if const.CLEAR_LOGS else None
    config_map = configparser.ConfigParser(allow_no_value=True)
    try:
        config_map.read(const.PATH_CONFIG)
    except KeyError:
        write_default_configurations(const.PATH_CONFIG)
        config_map.read(const.PATH_CONFIG)

    set_constants(config_map)
    const.THIS_IP = get_ip()
    const.IP_VERSION = (socket.AF_INET6
                        if ipaddress.ip_address(const.THIS_IP).version == 6
                        else socket.AF_INET)
    # print(f"{const.THIS_IP=}")
    validate_ports()
    write_port_to_js()  # just a convenience function of testing


def write_port_to_js():
    def free_port():
        while True:
            random_port = random.randint(1024, 65535)
            try:
                with soc.socket(const.IP_VERSION, const.PROTOCOL) as s:
                    s.bind(("localhost", random_port))
            except socket.error:
                pass
            else:
                return random_port

    import re
    # data = f"const addr = 'ws://localhost:{const.PORT_PAGE_DATA}';"
    # signals = f"const wss = new WebSocket(\"ws://localhost:{const.PORT_PAGE_SIGNALS}\");"
    const.PORT_PAGE_SIGNALS, const.PORT_PAGE_DATA = free_port(), free_port()
    perform_signals = os.path.join(const.PATH_PAGE, 'perform_signals.js')
    perform_data = os.path.join(const.PATH_PAGE, 'perform_data.js')

    with open(perform_signals, 'r') as file:
        pattern = r'const wss = new WebSocket\("ws://localhost:\d+"\);'
        line = f'const wss = new WebSocket("ws://localhost:{const.PORT_PAGE_SIGNALS}");'

        lines = file.readlines()
        lines[1] = re.sub(pattern, line, lines[1])

    with open(perform_signals, 'w') as file:
        file.writelines(lines)

    with open(perform_data, 'r') as file:
        pattern = r'const addr = "ws://localhost:\d+";'
        line = f"const addr = \"ws://localhost:{const.PORT_PAGE_DATA}\";"

        lines = file.readlines()

        lines[1] = re.sub(pattern, line, lines[1])
    with open(perform_data, 'w') as file:
        file.writelines(lines)


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
        return get_v4() or '127.0.0.1'
    elif const.IP_VERSION == soc.AF_INET6:
        if soc.has_ipv6:
            return get_v6() or '::1'

    return '127.0.0.1'


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
        back_up = ""
        for sock_tuple in soc.getaddrinfo("", None, soc.AF_INET6, proto=const.PROTOCOL, flags=soc.AI_PASSIVE):
            ip, _, _, _ = sock_tuple[4]
            if ipaddress.ip_address(ip).is_link_local:
                back_up = ip
            elif not ipaddress.ip_address(ip).is_link_local:
                return ip
        return back_up
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
                ip_v6.append(line.split()[1].split('/')[0])
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


def initiate_this_object():
    const.THIS_OBJECT = RemotePeer(const.USERNAME, const.THIS_IP, const.PORT_THIS, report=const.PORT_REQ, status=1)


def clear_logs():
    with open(os.path.join(const.PATH_LOG, 'error.logs'), 'w') as e:
        e.write('')
    with open(os.path.join(const.PATH_LOG, 'activity.logs'), 'w') as a:
        a.write('')
    with open(os.path.join(const.PATH_LOG, 'server.logs'), 'w') as s:
        s.write('')


def write_default_configurations(path):
    default_config_file = (
        '[NERD_OPTIONS]\n'
        'this_port = 48221\n'
        'page_port = 12260\n'
        'page_port_signals = 42057\n'
        'ip_version = 4\n'
        'protocol = tcp\n'
        'req_port = 35623\n'
        'file_port = 35621\n'
        'page_serve_port = 40000\n'
        '\n'
        '[USER_PROFILES]\n'
        'admin\n'
    )
    default_profile_file = (
        '[USER]\n'
        'name = admin\n'
        '\n'
        '[SERVER]\n'
        'port = 45000\n'
        'ip = 0.0.0.0\n'
        'id = 0\n'
    )

    with open(path, 'w+') as config_file:
        config_file.write(default_config_file)
    with open(os.path.join(const.PATH_PROFILES, 'admin.ini'), 'w+') as profile_file:
        profile_file.write(default_profile_file)


def validate_ports() -> None:
    ports_list = [const.PORT_THIS, const.PORT_PAGE_DATA, const.PORT_PAGE_SIGNALS, const.PORT_REQ,
                  const.PORT_FILE]
    for i, port in enumerate(ports_list):
        if not is_port_empty(port):
            ports_list[i] = src.avails.connect.get_free_port()
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

        return path.strip().split('"')[1]

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

    except FileNotFoundError:
        from src.avails.useables import echo_print
        echo_print("::webpage not found, look's like the package you downloaded is corrupted")
