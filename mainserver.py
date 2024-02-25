import socket as soc
import threading
import signal
import struct
import pickle
import requests
import select
import queue
from avails.textobject import PeerText
import avails.remotepeer as rp
import avails.constants as const

SAFE = threading.Lock()
SERVEROBJ = None
IPVERSION = soc.AF_INET
PROTOCOL = soc.SOCK_STREAM
handshakemessage = 'connectionaccepted'
print('::starting server')
EXIT = threading.Event()
LIST: set[rp.RemotePeer] = set()


# LIST.add(rp.RemotePeer(username='temp',port=25006,ip='1.1.1.1',status=1))
def get_local_ip():
    s = soc.socket(IPVERSION, PROTOCOL)
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
LeftPeer = queue.Queue()


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


def sendlist(client: soc.socket):
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


def validate2(client: soc.socket):
    global handshakemessage
    try:
        _newuser = rp.deserialize(client)
        print('::got new user :', _newuser, 'status :', _newuser.status)
        with SAFE:
            if _newuser.status == 0:
                print('::removing user :', _newuser)
                LIST.discard(_newuser)
                print("new list :", LIST)
                return True
        # PeerText(client,const.SERVEROK).send()
        PeerText(client, "getanother").send()
        _toget = rp.RemotePeer('babu', getip()[0], 12000, 56823, 1)
        _toget.serialize(client)
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
            return config_ip, 45000
    config_PUBILC_DNS = "1.1.1.1"
    config_soc.connect((config_PUBILC_DNS, 80))
    config_ip = config_soc.getsockname()[0]

    return config_ip, 45000


def start_server():
    global SERVEROBJ
    _server = soc.socket(IPVERSION, PROTOCOL)
    _server.bind(getip())
    _server.listen()
    SERVEROBJ = _server
    print("Server started at:\n>>", _server.getsockname())
    while not EXIT.is_set():
        readable, _, _ = select.select([_server], [], [], 0.001)
        if _server in readable:
            client, addr = _server.accept()
            validate(client)


def endserver(signum, frame):
    print("\nExiting from application...")
    EXIT.set()
    SERVEROBJ.close()
    return


def getlist(lis):
    for i in range(len(lis)):
        l = lis[i]
        lis[i] += 1
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