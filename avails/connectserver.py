import socket
import time
from core import constants as const
import struct
import logs
import threading
import pickle
import webpage

SocketMain = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ListOfPeer = set()
SafeStop = True


def getlistfromserver():
    global SocketMain, ListOfPeer, SafeStop
    _n = SocketMain.recv(4)
    _l = struct.unpack('!I', _n)[0]

    for _ in range(_l):

        try:
            lenofpeer = struct.unpack('!I',SocketMain.recv(4))[0]
            _nomad = pickle.loads(SocketMain.recv(lenofpeer))
            webpage.handle.feedserverdata(_nomad, True)
        except Exception as e:
            logs.errorlog("::Exception while recieving list of users:" + str(e))

    while SafeStop:

        try:
            n = struct.unpack('!I',SocketMain.recv(4))[0]
            status:bool = pickle.loads(SocketMain.recv(5))
            newpeer = pickle.loads(SocketMain.recv(n - 5))
        except Exception as e:
            logs.errorlog("::Exception with new user data:" + str(e))
            continue
    return


def start_thread(threadfunc: callable):
    thread = threading.Thread(target=threadfunc, daemon=True)
    thread.start()
    return thread


def initiateconnection():
    global SocketMain

    while True:

        try:
            print("::Connecting to server :",const.SERVERIP, const.SERVERPORT)
            SocketMain.connect((const.SERVERIP, const.SERVERPORT))
            _packet = pickle.dumps(const.SERVEDATA)
            _prerequisites = struct.pack('!I', len(_packet))
            SocketMain.sendall(_prerequisites)
            SocketMain.sendall(_packet)
            _l = struct.unpack('!I', SocketMain.recv(4))[0]
            _data = SocketMain.recv(_l).decode(const.FORMAT)
            if _data == 'connectionaccepted':
                logs.serverlog('::Connection accepted by server',2)
            const.SERVERTHREAD = start_thread(getlistfromserver)
            return True
        except Exception as exp:
            logs.serverlog(f"::Connection failed, retrying...{exp}", 1)
            time.sleep(5)


def endconnection():
    global SocketMain, SafeStop
    SocketMain.send('leaving'.encode(const.FORMAT))
    print('::Disconnecting from server')
    SafeStop = False
    try:
        if SocketMain.close():
            return True
    except Exception as exp:
        logs.serverlog(f'::Failed disconnecting from server{exp}', 4)
