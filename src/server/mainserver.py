import socket as soc
import threading
import signal
import struct
import pickle
import time
from collections import deque
import requests
import select
from src.avails.textobject import SimplePeerText
import container
import src.avails.remotepeer as rp
import src.avails.constants as const

IPVERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM

SAFE_LOCK = threading.Lock()
SERVERPORT = 45000
SERVEROBJ = soc.socket(IPVERSION, PROTOCOL)
handshakemessage = 'connectionaccepted'
print('::starting server')
EXIT = threading.Event()
LIST = container.CustomSet()
# LIST.add(rp.RemotePeer(username='temp', port=25006, ip='1.1.1.1', status=1))
ip = ""


def get_local_ip():
    global ip
    s = soc.socket(IPVERSION, PROTOCOL)
    s.settimeout(0.5)
    try:
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
    except soc.error as e:
        print(f"::got {e} trying another way")
        ip = soc.gethostbyname(soc.gethostname())
    finally:
        print(f"Local IP: {ip}")
        s.close()
        return ip


def givelist(client: soc.socket, userobj: rp.RemotePeer):
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


def validate(client: soc.socket):
    global handshakemessage
    try:
        _newuser = rp.deserialize(client)
        print('::got new user :', _newuser, "ip: ", client.getsockname(), 'status :', _newuser.status)
        with SAFE_LOCK:
            if _newuser.status == 0:
                print('::removing user :', _newuser)
                LIST.discard(_newuser)
                print("new list :", LIST)
                return True
        SimplePeerText(client, const.SERVER_OK).send()
        threading.Thread(target=givelist, args=(client, _newuser)).start()
        return True
    except soc.error as e:
        print(f'::got {e} closing connection')
        client.close() if client else None
        return False


def getip():
    config_soc = soc.socket(IPVERSION, PROTOCOL)
    config_ip = ''
    if IPVERSION == soc.AF_INET6:
        response = requests.get('https://api64.ipify.org?format=json')
        if response.status_code == 200:
            data = response.json()
            config_ip = data['ip']
            return config_ip, SERVERPORT
    config_ip = get_local_ip()

    return config_ip, SERVERPORT


def give_chance(client: rp.RemotePeer):
    with SAFE_LOCK:
        if client not in LIST:
            LIST.add(client)
            return True
    return False


def sync_users():
    while not EXIT.is_set():
        if len(LIST) == 0:
            time.sleep(5)
            continue
        que = deque(LIST)
        filtered_changes = LIST.getchanges()
        while que:
            peer: rp.RemotePeer = que.popleft()
            active_user_sock = soc.socket(IPVERSION, PROTOCOL)
            active_user_sock.settimeout(5)
            try:
                active_user_sock.connect(peer.req_uri)
                SimplePeerText(active_user_sock, const.SERVER_PING, byte_able=False).send()
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
    const.THIS_IP, SERVERPORT = getip()
    SERVEROBJ.bind((const.THIS_IP, SERVERPORT))
    SERVEROBJ.listen()
    print("Server started at:\n>>", SERVEROBJ.getsockname())
    threading.Thread(target=sync_users).start()
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
