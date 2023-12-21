import os
import socket as soc
import threading
import signal
import struct
import pickle
from avails import Fluxuant
from avails.nomad import Nomad
import time

SAFE = threading.Lock()

handshakemessage = 'connectionaccepted'
EXIT = threading.Event()
LIST = Fluxuant()
LIST.add(pickle.dumps(Nomad.peer('temp', ('localhost', 7072))))


def get_local_ip():
    s = soc.socket(soc.AF_INET, soc.SOCK_STREAM)
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


Hold = True
LeftPeer = {}


def peerhandler(client: soc.socket):
    global LeftPeer, Hold
    while Hold:
        try:
            client.recv(4)
        except ConnectionResetError as e:
            return False, None


def signalit(userobject: Nomad.peer):
    global LeftPeer, Hold
    LeftPeer[userobject] = 0
    Hold = False
    return


def keepalive(client: soc.socket, userobject: Nomad.peer):
    while True:
        try:
            print('waiting for client to send keepalive')
            time.sleep(6)
            status, _servpeer = peerhandler(client)
            if _servpeer is None:
                raise ConnectionResetError('client disconnected')
            _servpeer = status.encode('utf-8') + pickle.dumps(_servpeer)
            client.sendall(struct.pack('!I', len(_servpeer)))
            client.sendall(_servpeer)
        except ConnectionResetError as e:
            LIST.discard(userobject)
            print(LIST)
            signalit(userobject)
            print(f'::got {e} closing connection')
            client.close()
            return
        except soc.error as e:
            print(f'::got {e} retrying connection')
        return


def givelist(client: soc.socket, userobject: Nomad.peer):
    if not isinstance(client, soc.socket):
        raise TypeError('client must be a socket')
    print('::sending list to client :', client.getpeername())
    if len(LIST) == 0:
        client.send(struct.pack('!I', 0))
        return
    client.send(struct.pack('!I', len(LIST)))
    for peers in LIST:
        with SAFE:
            client.send(struct.pack('!I', len(peers)))
            client.sendall(peers)
    print('::sent list to client :', client.getpeername())
    keepalive(client, userobject)
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
        _l = struct.unpack('!I', client.recv(4))[0]
        _newuser = client.recv(_l)
        th = threading.Thread(target=givelist, args=(client, _newuser))
        with SAFE:
            LIST.add(_newuser)
        client.send(struct.pack('!I', len(handshakemessage)) + handshakemessage.encode('utf-8'))
        th.start()
        return True
    except soc.error as e:
        print(f'::got {e} closing connection')
        client.close()
        return False


def start_server():
    server = soc.socket(soc.AF_INET, soc.SOCK_STREAM)
    server.bind(('localhost', 7070))
    server.listen()
    print("Server started at:\n>>", server.getsockname())
    while not EXIT.is_set():
        client, addr = server.accept()
        print(f"\tConnected to {addr}")
        validate(client)


def endserver():
    with EXIT:
        EXIT.set()


start_server()