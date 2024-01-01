import threading

import select

from core import *
from core.textobject import PeerText
import core.remotepeer as remote_peer
from webpage import handle
from logs import *

ListOfPeer = set()
Safe = threading.Event()
ErrorCalls = 0


def intiallist(noofusers: int, initiate_socket):
    global ListOfPeer, Safe, ErrorCalls
    if noofusers != 0:
        for _ in range(noofusers):

            try:
                readables, _, _ = select.select([initiate_socket], [], [], 0.001)
                if initiate_socket in readables:
                    _nomad = remote_peer.deserialize(initiate_socket)
                    ListOfPeer.add(_nomad) if _nomad.status == 1 else ListOfPeer.discard(_nomad)
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


def getlistfrom(initiate_socket):
    const.HANDLECALL.wait()
    global ListOfPeer, Safe, ErrorCalls
    rawlength = 0
    for _ in range(const.MAXCALLBACKS):
        try:
            readables, _, _ = select.select([initiate_socket], [], [], 0.001)
            if initiate_socket in readables:
                rawlength = initiate_socket.recv(8)
                break
        except socket.error as e:
            # logs.errorlog("::Exception while recieving list of users:" + str(e))
            print(f"::Exception while recieving list of users: retrying... {e}")
            continue

    return intiallist(struct.unpack('!Q', rawlength)[0], initiate_socket)


def give_list():
    list_soc = socket.socket(const.IPVERSION, const.PROTOCOL)
    list_soc.bind((const.THISIP, const.REQPORT))
    list_soc.listen(5)
    while not Safe.is_set():
        readables, _, _ = select.select([list_soc], [], [], 0.001)
        if list_soc not in readables:
            continue
        peer, addr = list_soc.accept()
        for _nomad in ListOfPeer:
            if not Safe.is_set():
                return
            if _nomad.status == 1:
                try:
                    _nomad.serialize(peer)
                except socket.error as e:
                    # logs.errorlog(f"::Exception while giving list of users: {e}")
                    print(f"::Exception while giving list of users: {e}")
                    continue


def initiateconnection():
    global ListOfPeer, Safe, ErrorCalls
    threading.Thread(target=give_list).start()
    while not Safe.is_set():

        try:
            InitiateSocket = socket.socket(const.IPVERSION, const.PROTOCOL)
            InitiateSocket.connect((const.SERVERIP, const.SERVERPORT))
            const.REMOTEOBJECT.serialize(InitiateSocket)
            if PeerText(InitiateSocket).receive(cmpstring=const.SERVEROK):
                # logs.serverlog('::Connection accepted by server', 2)
                print('::Connection accepted by server')
                threading.Thread(target=getlistfrom, args=(InitiateSocket,)).start()
            else:
                recv_list_user = remote_peer.deserialize(InitiateSocket)
                ListOfPeer.add(recv_list_user)
                InitiateSocket.close()
                InitiateSocket = socket.socket(const.IPVERSION, const.PROTOCOL)
                InitiateSocket.connect(recv_list_user.requri)
                PeerText(InitiateSocket, const.REQFORLIST).send()
                print(f"::Connecting to {InitiateSocket.getpeername()}, getting list")
                threading.Thread(target=getlistfrom, args=(InitiateSocket,)).start()
                if recv_list_user.status == 1:
                    pass
            return True
        except socket.error as exp:
            # logs.serverlog(f"::Connection failed, retrying...{exp}", 1)
            print(f"::Connection failed, retrying...{exp}")
            if exp.errno == 10056:
                return False
            time.sleep(5)


def endconnection():
    global Safe, ListOfPeer
    print('::Disconnecting from server')
    Safe.set()
    try:
        const.REMOTEOBJECT.status = 0
        EndSocket = socket.socket(const.IPVERSION, const.PROTOCOL)
        EndSocket.connect((const.SERVERIP, const.SERVERPORT))
        if const.REMOTEOBJECT.serialize(EndSocket):
            EndSocket.close() if EndSocket else None
        ListOfPeer.clear()
        Safe = threading.Event()
    except Exception as exp:
        # serverlog(f'::Failed disconnecting from server{exp}', 4)
        print(f'::Failed closing server{exp}')
