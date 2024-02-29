import socket as soc
import threading
import signal
import struct
import pickle
import time
import requests
import select
from avails.textobject import PeerText
import container
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
            listcopy = LIST.copy()
            for peer in listcopy:
                active_user_sock = soc.socket(IPVERSION, PROTOCOL)
                active_user_sock.settimeout(1)
                try:
                    active_user_sock.connect(peer.req_uri)
                    PeerText(active_user_sock, const.SERVER_PING, byteable=False).send()
                except soc.error as e:
                    print(f'::got EXCEPTION closing connection with :', peer)
                    print('::new list :', LIST)
                    LIST.discard(peer)
                    peer.status = 0
                    continue
                active_user_sock.send(struct.pack('!I', len(LIST.removedchanges())))
                for peer in LIST.removes:
                    peer.serialize(active_user_sock)
                active_user_sock.close()

        except RuntimeError as e:
            print(f'::got {e} trying again')
            continue
        time.sleep(5)


def start_server():
    global SERVEROBJ
    SERVEROBJ.setsockopt(soc.SOL_SOCKET, soc.SO_REUSEADDR, 1)
    const.THISIP, SERVERPORT_ = getip()
    SERVEROBJ.bind((const.THIS_IP, SERVERPORT_))
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
