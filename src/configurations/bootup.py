import configparser
import ipaddress
import json
import os
import socket
import subprocess
import urllib.request
import webbrowser

from src.avails import (
    RemotePeer,
    const,
    connect,
    use,
)
from ..avails.useables import echo_print
from ..configurations.configure import set_constants
import src.core.eventloop
from ..core.peers import set_current_remote_peer_object


def initiate_bootup():
    clear_logs() if const.CLEAR_LOGS else None
    config_map = configparser.ConfigParser(allow_no_value=True)
    try:
        config_map.read(const.PATH_CONFIG)
    except KeyError:
        write_default_configurations(const.PATH_CONFIG)
        config_map.read(const.PATH_CONFIG)

    set_constants(config_map)
    const.THIS_IP, const.IP_VERSION = get_ip()
    const.IP_VERSION = (socket.AF_INET6
                        if ipaddress.ip_address(const.THIS_IP).version == 6
                        else socket.AF_INET)
    # print(f"{const.THIS_IP=}")
    const.THIS_IP = '172.16.199.138'  # todo remove this ip in bootup.py
    validate_ports()


def get_ip() -> tuple[str, int]:
    """
    Retrieves the local IP address of the machine.
    If unsuccessful, falls back to using gethostbyname().

    Returns:
        str: The local IP address as a string.

    Raises:
        socket.error: If a socket error occurs during connection.
    """
    if const.IP_VERSION == socket.AF_INET:
        return (get_v4() or '127.0.0.1'), socket.AF_INET

    ip_addr, version = str, int
    if const.IP_VERSION == socket.AF_INET6:
        if socket.has_ipv6:
            if ip := get_v6():
                ip_addr, version = ip, socket.AF_INET6
            else:
                if ip := get_v4():
                    ip_addr, version = ip, socket.AF_INET
                else:
                    ip_addr, version = '::1', socket.AF_INET
        else:
            ip_addr, version = (get_v4() or '127.0.0.1'), socket.AF_INET
    return ip_addr, version


def get_v4():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as config_socket:
        try:
            config_socket.connect(('1.1.1.1', 80))
            config_ip = config_socket.getsockname()[0]
        except (OSError, socket.error) as e:
            # error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")

            config_ip = socket.gethostbyname(socket.gethostname())
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
        back_up = "::1"
        for sock_tuple in socket.getaddrinfo("", None, socket.AF_INET6):
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
        result = subprocess.run(['ip', '-6', 'addr', 'show'], capture_output=True, text=True)
        output_lines = result.stdout.split('\n')

        ip_v6 = []
        for line in output_lines:
            if 'inet6' in line and 'fe80' not in line and '::1' not in line:
                ip_v6.append(line.split()[1].split('/')[0])
    except Exception as exp:
        print(f"Error occurred: {exp}")
        return
    return ip_v6[0]


def get_v6_from_api64():
    config_ip = "::1"  # Default IPv6 address

    try:
        with urllib.request.urlopen('https://api64.ipify.org?format=json') as response:
            data = response.read().decode('utf-8')
            data_dict = json.loads(data)
            config_ip = data_dict.get('ip', config_ip)
    except (urllib.request.HTTPError, json.JSONDecodeError) as e:
        # error_log(f"Error getting local ip: {e} from get_local_ip() at line 40 in core/constants.py")
        config_ip = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6)[0][4][0]

    return config_ip


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
        'id = 1234'
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
    ports_list = [const.PORT_THIS, const.PORT_PAGE, const.PORT_REQ,
                  const.PORT_FILE, const.PORT_NETWORK]
    for i, port in enumerate(ports_list):
        if not connect.is_port_empty(port):
            ports_list[i] = connect.get_free_port()
            echo_print(f"Port is not empty. choosing another port: {ports_list[i]}")
    const.PORT_THIS, const.PORT_PAGE, const.PORT_REQ, const.PORT_FILE, const.PORT_NETWORK = ports_list
    return None


@use.NotInUse
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
