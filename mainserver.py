import socket as soc
import threading
import signal
import struct
import pickle
import time
import requests
import select
from avails.textobject import PeerText
import avails.remotepeer as rp
import avails.constants as const

IPVERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM

SAFE = threading.Lock()
SERVERPORT = 45000
SERVEROBJ = soc.socket(IPVERSION, PROTOCOL)
handshakemessage = 'connectionaccepted'
print('::starting server')
EXIT = threading.Event()
LIST: set[rp.RemotePeer] = set()
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


LeftPeerSafe = threading.Lock()
synclist: set[rp.RemotePeer] = set()


def givelist(client: soc.socket, userobj: rp.RemotePeer):
    if not isinstance(client, soc.socket):
        raise TypeError('client must be a socket')
    client.send(struct.pack('!Q', len(LIST)))
    for peers in LIST:
        with SAFE:
            peers.serialize(client)
    LIST.add(userobj)
    print('::sent list to client :', client.getpeername())
    print('::new list :', LIST)
    return


def sendlist(client: soc.socket, ):
    """Another implementation of sending a list not in use currently"""
    with SAFE:
        _l = struct.pack('!I', len(LIST))
        client.send(_l)
        client.sendall(pickle.dumps(LIST))


def validate(client: soc.socket):
    global handshakemessage
    try:
        _newuser = rp.deserialize(client)
        print('::got new user :', _newuser, "ip: ", client.getsockname(), 'status :', _newuser.status)
        with SAFE:
            if _newuser.status == 0:
                print('::removing user :', _newuser)
                LIST.discard(_newuser)
                synclist.add(_newuser)
                print("new list :", LIST)
                return True
        PeerText(client, const.SERVER_OK).send()
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


def sync_users():
    while not EXIT.is_set():
        if len(LIST) == 0:
            time.sleep(5)
            continue
        try:
            for peer in LIST:

                active_user_sock = soc.socket(IPVERSION, PROTOCOL)
                active_user_sock.settimeout(0.5)
                try:
                    active_user_sock.connect(peer.req_uri)
                    PeerText(active_user_sock, const.SERVER_PING, byteable=False).send()
                except soc.error as e:
                    print(f'::got EXCEPTION closing connection with :', peer)
                    print('::new list :', LIST)
                    LIST.discard(peer)
                    peer.status = 0
                    synclist.add(peer)
                    continue
                # print(f'::sending size of {len(synclist)} list to :', peer)
                active_user_sock.send(struct.pack('!I', len(synclist)))
                for peers in synclist:
                    peers.serialize(active_user_sock)
                active_user_sock.close()
            print('::synced list :', LIST)
            synclist.clear()
        except RuntimeError as e:
            print(f'::got {e} trying again')
            continue
        time.sleep(5)


def start_server():
    global SERVEROBJ
    SERVEROBJ.setsockopt(soc.SOL_SOCKET, soc.SO_REUSEADDR, 1)
    SERVEROBJ.bind(getip())
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
"""

import socket,select,signal
import requests
from server.core.textobject import PeerText
stop = True
def endserver(signum, frame):
    global stop
    print("\nExiting from application...")
    stop = False
    return
soc = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
config_ip = ''
response = requests.get('https://api64.ipify.org?format=json')
if response.status_code == 200:
    data = response.json()
    config_ip = data['ip']
print(config_ip)
soc.bind((config_ip, 25006))
soc.listen()
signal.signal(signal.SIGINT, endserver)
print('listening at',soc.getsockname())
while stop:
    readable, _,_= select.select([soc], [], [], 0.1)
    if soc not in readable:
        continue
    client, addr = soc.accept()
    print('accepted',client.getpeername())
    print(PeerText(client).receive())
    client.close()



"""
