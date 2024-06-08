import ipaddress
import socket as soc
import threading
import signal
import struct
import pickle
import time
from collections import deque
import select

import urllib3
from src.avails.connect import Socket
from src.avails.container import SafeSet
from src.avails.textobject import SimplePeerText, DataWeaver
from src.avails.remotepeer import RemotePeer
import src.avails.constants as const
import json
import subprocess

IP_VERSION = soc.AF_INET6
PROTOCOL = soc.SOCK_STREAM
PUBLIC_IP = '8.8.8.8'
SAFE_LOCK = threading.Lock()
SERVERPORT = 45000
SERVEROBJ = Socket(IP_VERSION, PROTOCOL)
handshakemessage = 'connectionaccepted'
print('::starting server')
EXIT = threading.Event()
LIST = SafeSet()
# LIST.add(rp.RemotePeer(username='temp', port=25006, ip='1.1.11.1', status=1))
ip = ""


def get_ip():
    """Retrieves the local IP address of the machine.

    Attempts to connect to a public DNS server (1.1.1.1) to obtain the local IP.
    If unsuccessful, falls back to using gethostbyname().

    Returns:
        str: The local IP address as a string.

    Raises:
        soc.error: If a socket error occurs during connection.
    """
    if IP_VERSION == soc.AF_INET:
        return get_v4() or '127.0.0.1', SERVERPORT
    elif IP_VERSION == soc.AF_INET6:
        if soc.has_ipv6:
            return get_v6() or '::1', SERVERPORT

    # return '127.0.0.1', SERVERPORT


def get_v4():
    with soc.socket(soc.AF_INET, soc.SOCK_DGRAM) as config_soc:
        try:
            config_soc.connect(('1.1.1.1', 80))
            config_ip = config_soc.getsockname()[0]
        except soc.error as e:
            print("error gettting ip")
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
                ip_v6.append(line.split()[1])
    except Exception as exp:
        print(f"Error occurred: {exp}")
        return []
    return ip_v6[0]


def get_v6_from_api64():
    config_ip = "::1"  # Default IPv6 address
    try:
        with urllib3.request('GET','https://api64.ipify.org?format=json') as response:
            data = response.read().decode('utf-8')
            data_dict = json.loads(data)
            config_ip = data_dict.get('ip', config_ip)
    except json.JSONDecodeError:
        config_ip = soc.getaddrinfo(soc.gethostname(), None, soc.AF_INET6)[0][4][0]

    return config_ip


def givelist(client: soc.socket, userobj: RemotePeer):
    if not isinstance(client, soc.socket):
        raise TypeError('client must be a socket')
    client.send(struct.pack('!Q', len(LIST)))
    for peers in LIST:
        with SAFE_LOCK:
            peers.serialize(client)
    LIST.add(userobj)
    print('::sent list to client :', client.getpeername())
    print('::new list :', LIST)
    return


def sendlist(client: soc.socket, ):
    """Another implementation of sending a list not in use currently"""
    with SAFE_LOCK:
        _l = struct.pack('!I', len(LIST))
        client.send(_l)
        client.sendall(pickle.dumps(LIST))


def validate(client):
    global handshakemessage
    try:
        _newuser = RemotePeer.deserialize(client)
        print('::got new user :', _newuser, "ip: ", client.getsockname(), 'status :', _newuser.status)
        with SAFE_LOCK:
            if _newuser.status == 0:
                print('::removing user :', _newuser)
                LIST.discard(_newuser)
                print("new list :", LIST)
                return True
        LIST.discard(_newuser, False)
        SimplePeerText(client, const.SERVER_OK).send()
        threading.Thread(target=givelist, args=(client, _newuser)).start()
        return True
    except soc.error as e:
        print(f'::got {e} closing connection')
        client.close() if client else None
        return False


def sync_users():
    while not EXIT.is_set():
        if len(LIST) == 0:
            time.sleep(5)
            continue
        que = deque(LIST)
        filtered_changes = LIST.getchanges()
        while que:
            peer: RemotePeer = que.popleft()
            active_user_sock = soc.socket(IP_VERSION, PROTOCOL)
            active_user_sock.settimeout(5)
            try:
                active_user_sock.connect(peer.req_uri)
                SimplePeerText(active_user_sock, const.SERVER_PING).send()
            except soc.error as e:
                print(f'::got EXCEPTION {e} closing connection with :', peer)
                peer.status = 0
                LIST.sync_remove(peer)
                continue
            if len(filtered_changes) == 0:
                active_user_sock.send(struct.pack('!Q', 0))
            else:
                give_changes(active_user_sock, filtered_changes)
        time.sleep(5)


def give_changes(active_user_sock: soc.socket, changes: deque):
    # print(f'::give_changes called :{active_user_sock.getpeername()}', changes)
    try:
        with active_user_sock:
            active_user_sock.send(struct.pack('!Q', len(changes)))
            for _peer in changes:
                _peer.serialize(active_user_sock)
    except soc.error as e:
        print(f'::got {e} for active user :', active_user_sock.getpeername())


def start_server():
    global SERVEROBJ
    SERVEROBJ.setsockopt(soc.SOL_SOCKET, soc.SO_REUSEADDR, 1)
    _ip, port = get_ip()
    print(get_ip())
    SERVEROBJ.bind((_ip, port))
    SERVEROBJ.listen()
    print("Server started at:\n>>", SERVEROBJ.getsockname())
    # threading.Thread(target=sync_users).start()
    while not EXIT.is_set():
        readable, _, _ = select.select([SERVEROBJ], [], [], 0.001)
        if SERVEROBJ in readable:
            client, addr = SERVEROBJ.accept()
            print("A connection from :", addr)
            validate(client)


def endserver(signum, frame):
    print("\nExiting from application...")
    EXIT.set()
    SERVEROBJ.close()
    return


def getlist(lis):
    return


if __name__ == '__main__':
    signal.signal(signal.SIGINT, endserver)
    start_server()
