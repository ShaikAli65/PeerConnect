import socket
import time
import struct
import logs
import threading
import pickle
import asyncio


from core import constants as const
from webpage import handle
from queue import Queue


SocketMain = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ListOfPeer = set()
Saferecv = threading.Event()
ErrorCalls = 0
CallQueue = Queue()


def recvintiallist(nofusers:int):
    global SocketMain, ListOfPeer, Saferecv, ErrorCalls
    _numberofusers = nofusers
    if _numberofusers != 0:
        for _ in range(_numberofusers):

            try:
                lenofpeer = struct.unpack('!I', SocketMain.recv(4))[0]
                _nomad = pickle.loads(SocketMain.recv(lenofpeer))
                asyncio.run(handle.feedserverdata(_nomad, 1))
            except socket.error as e:
                logs.errorlog("::Exception while recieving list of users:" + str(e))
                if e.errno == 10054:
                    time.sleep(5)
                    # logs.serverlog(f"::Server disconnected retrycount :{_}", 4)
                    print("::Server disconnected retrying...")
                    return False
    return False


def keeprecieving():
    global SocketMain, ListOfPeer, Saferecv, ErrorCalls
    while not Saferecv.isSet():

        try:
            n = struct.unpack('!I', SocketMain.recv(4))[0]
            status = SocketMain.recv(1).decode(const.FORMAT)
            newpeer = pickle.loads(SocketMain.recv(n - 1))
            print("databout peer :", status, newpeer)
            asyncio.run(handle.feedserverdata(newpeer, status=status))
        except socket.error as e:
            if e.errno == 10054:
                # logs.serverlog(f"::Server disconnected CallCount{ErrorCalls} ", 4)
                print("::Server disconnected retrying... ErrorCalls :", ErrorCalls)
                time.sleep(5)
                return False
            else:
                logs.errorlog("::Exception with new user data:" + str(e))
            continue
    return True


def getlistfromserver():
    global SocketMain, ListOfPeer, Saferecv, ErrorCalls
    rawlength = 0
    for _ in range(const.MAXCALLBACKS):
        try:
            rawlength = SocketMain.recv(4)
            break
        except socket.error as e:
            # logs.errorlog("::Exception while recieving list of users:" + str(e))
            print(f"::Exception while recieving list of users: retrying... {e}")
            continue

    _numberofusers = struct.unpack('!I', rawlength)[0]
    print("number of initial users :", _numberofusers)
    if not recvintiallist(_numberofusers):
        return

    if not keeprecieving():
        return


def start_thread(threadfunc: callable):
    thread = threading.Thread(target=threadfunc, daemon=True)
    thread.start()
    thread = threading.Thread(target=threadfunc, daemon=True)
    thread.start() if CallQueue.get() is False else None
    return thread


def initiateconnection():
    global SocketMain

    while not Saferecv.isSet():

        try:
            print("::Connecting to server :", const.SERVERIP, const.SERVERPORT)
            SocketMain.connect((const.SERVERIP, const.SERVERPORT))
            _packet = pickle.dumps(const.SERVEDATA)
            _prerequisites = struct.pack('!I', len(_packet))
            SocketMain.sendall(_prerequisites)
            SocketMain.sendall(_packet)
            _l = struct.unpack('!I', SocketMain.recv(4))[0]
            _data = SocketMain.recv(_l).decode(const.FORMAT)
            if _data == 'connectionaccepted':
                # logs.serverlog('::Connection accepted by server', 2)
                print('::Connection accepted by server')
            const.SERVERTHREAD = start_thread(getlistfromserver)
            return True
        except Exception as exp:
            # logs.serverlog(f"::Connection failed, retrying...{exp}", 1)
            print(f"::Connection failed, retrying...{exp}")
            time.sleep(5)


def endconnection():
    global SocketMain, Saferecv
    print('::Disconnecting from server')
    Saferecv.set()
    try:
        SocketMain.close()
        logs.serverlog('::Disconnected from server', 2)
    except Exception as exp:
        logs.serverlog(f'::Failed disconnecting from server{exp}', 4)
