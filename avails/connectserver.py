import socket
import time
import constants as const
import struct
import logs
import threading

SocketMain = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ListOfPeer = set[tuple[str, int]]
SafeStop = True


def getlistfromserver():
    global SocketMain, ListOfPeer, SafeStop
    n = eval(SocketMain.recv(4).decode(const.FORMAT))
    length = struct.unpack('!I', n)[0]
    ListOfPeer = eval(SocketMain.recv(length).decode(const.FORMAT))
    while SafeStop:
        n: int = eval(SocketMain.recv(4).decode(const.FORMAT))
        newpeer:tuple[bool,tuple[str,int]] = eval(SocketMain.recv(struct.unpack('!I', n)[0]).decode(const.FORMAT))
        if newpeer[0]:
            ListOfPeer.add(newpeer[1])
        else:
            ListOfPeer.remove(newpeer[1])
    return


def start_thread(threadfunc: callable):
    thread = threading.Thread(target=threadfunc, daemon=True)
    thread.start()
    return thread


def connectpeers(peerdata: tuple[str, int] = None):
    global SocketMain, ListOfPeer
    thread = threading.Thread(target=getlistfromserver, daemon=True)
    const.SERVERTHREAD = start_thread(thread)
    peersocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        if peerdata in ListOfPeer:
            peersocket.connect(peerdata)
    except Exception as exp:
        logs.serverlog(f'connection to peer :{peerdata} failed{exp}', 4)
    return


def initiateconnection():
    global SocketMain
    SocketMain.bind((const.THISIP, const.THISPORT))
    SocketMain.settimeout(4)
    while True:
        try:
            print("::Connecting to server :",const.SERVERIP, const.SERVERPORT)
            SocketMain.connect((const.SERVERIP, const.SERVERPORT))
            print("::Connection to server succeeded")
            _prerequisites = struct.pack('!I', len(f'{(const.THISIP, const.THISPORT)}'))
            SocketMain.sendall(_prerequisites)
            SocketMain.sendall(f'{(const.THISIP, const.THISPORT)}'.encode(const.FORMAT))
            connectpeers()

            return True
        except Exception as exp:
            time.sleep(2)
            logs.serverlog(f"Connection failed, retrying...{exp}", 1)


def endconnection():
    global SocketMain, SafeStop
    SocketMain.send('leaving'.encode(const.FORMAT))
    print('::Disconnecting from server')
    SafeStop = False
    try:
        if SocketMain.close():
            return True
    except Exception as exp:
        logs.serverlog(f'Failed disconnecting from server{exp}', 4)
