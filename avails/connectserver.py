import socket

import select

from core import *
from core.textobject import PeerText
import core.remotepeer as remote_peer
from webpage import handle
from logs import *


SocketMain = socket.socket(const.IPVERSION, const.PROTOCOL)
ListOfPeer = set()
Saferecv = threading.Event()
ErrorCalls = 0


def intiallist(noofusers:int):
    global SocketMain, ListOfPeer, Saferecv, ErrorCalls
    if noofusers != 0:
        for _ in range(noofusers):

            try:
                readables, _, _ = select.select([SocketMain], [], [], 0.001)
                if SocketMain in readables:
                    _nomad = remote_peer.deserialize(SocketMain)
                    ListOfPeer.add(_nomad) if _nomad.status == 1 else ListOfPeer.discard(_nomad)
                    print("::Recieved user :", _nomad.username, _nomad.uri)
                    asyncio.run(handle.feedserverdata(_nomad))
            except socket.error as e:
                errorlog("::Exception while recieving list of users:" + str(e))
                if e.errno == 10054:
                    time.sleep(5)
                    endconnection()

                    # logs.serverlog(f"::Server disconnected retrycount :{_}", 4)
                    initiateconnection()
                    return False
    return True


def getlistfromserver():
    const.HANDLECALL.wait()
    global SocketMain, ListOfPeer, Saferecv, ErrorCalls
    rawlength = 0
    for _ in range(const.MAXCALLBACKS):
        try:
            readables, _, _ = select.select([SocketMain], [], [], 0.001)
            if SocketMain in readables:
                rawlength = SocketMain.recv(8)
                break
        except socket.error as e:
            # logs.errorlog("::Exception while recieving list of users:" + str(e))
            print(f"::Exception while recieving list of users: retrying... {e}")
            continue

    _numberofusers = struct.unpack('!Q', rawlength)[0]
    print("number of initial users :", _numberofusers)
    return intiallist(_numberofusers)


def initiateconnection():
    global SocketMain
    while not Saferecv.isSet():

        try:
            print("::Connecting to server :", const.SERVERIP, const.SERVERPORT)
            SocketMain.connect((const.SERVERIP, const.SERVERPORT))
            const.REMOTEOBJECT.serialize(SocketMain)
            if PeerText(SocketMain).receive(cmpstring=const.SERVEROK):
                # logs.serverlog('::Connection accepted by server', 2)
                print('::Connection accepted by server')
            threading.Thread(target=getlistfromserver).start()
            return True
        except socket.error as exp:
            # logs.serverlog(f"::Connection failed, retrying...{exp}", 1)
            print(f"::Connection failed, retrying...{exp}")
            if exp.errno == 10056:
                return False
            time.sleep(5)


def endconnection():
    global SocketMain, Saferecv
    print('::Disconnecting from server')
    Saferecv.set()
    try:
        const.REMOTEOBJECT.status = 0
        SocketMain.close()
        dis_soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dis_soc.connect((const.SERVERIP, const.SERVERPORT))
        if const.REMOTEOBJECT.serialize(dis_soc):
            dis_soc.close() if dis_soc else None
        ListOfPeer.clear()
        Saferecv = threading.Event()
        # serverlog('::Disconnected from server', 2)
        print('::Disconnected from server')
    except Exception as exp:
        # serverlog(f'::Failed disconnecting from server{exp}', 4)
        print(f'::Failed disconnecting from server{exp}')