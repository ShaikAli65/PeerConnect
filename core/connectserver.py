import select
import main
from core import *
from avails.textobject import PeerText
import avails.remotepeer as remote_peer
from webpage import handle
from logs import *

Safe = threading.Event()
ErrorCalls = 0


def initial_list(no_of_users: int, initiate_socket):
    global Safe, ErrorCalls
    initial_list_peer = const.LISTOFPEERS
    count_of_user = 0
    if no_of_users == 0:
        return False
    for _ in range(no_of_users):

        try:
            readables, _, _ = select.select([initiate_socket], [], [], 0.001)
            if initiate_socket not in readables:
                continue
            _nomad:remote_peer.RemotePeer = remote_peer.deserialize(initiate_socket)
            _nomad.id = str(count_of_user)
            if _nomad.status == 1:
                initial_list_peer[count_of_user] = _nomad
            else:
                del initial_list_peer[count_of_user]
            count_of_user += 1
            asyncio.run(handle.feed_server_data(_nomad))

        except socket.error as e:
            errorlog("::Exception while recieving list of users:" + str(e))
            if e.errno == 10054:
                time.sleep(5)
                endconnection()

                # logs.serverlog(f"::Server disconnected retrycount :{_}", 4)
                initiate_connection()
                return False

    return True


def getlistfrom(initiate_socket):
    const.HANDLECALL.wait()
    global Safe, ErrorCalls
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

    return initial_list(struct.unpack('!Q', rawlength)[0], initiate_socket)


def give_list():
    list_soc = socket.socket(const.IPVERSION, const.PROTOCOL)
    # list_soc.bind((const.THISIP, const.REQPORT))
    # list_soc.listen(5)
    while not Safe.is_set():
        readables, _, _ = select.select([list_soc], [], [], 0.001)
        if list_soc not in readables:
            continue
        peer, addr = list_soc.accept()
        for _nomad in const.LISTOFPEERS.values():
            if not Safe.is_set():
                return
            if _nomad.status == 1:
                try:
                    _nomad.serialize(peer)
                except socket.error as e:
                    # logs.errorlog(f"::Exception while giving list of users: {e}")
                    print(f"::Exception while giving list of users: {e}")
                    continue


def initiate_connection():
    global Safe, ErrorCalls
    threading.Thread(target=give_list).start()
    callcount = 0
    while not Safe.is_set():

        try:
            initiate_connection_socket = socket.socket(const.IPVERSION, const.PROTOCOL)
            initiate_connection_socket.connect((const.SERVERIP, const.SERVERPORT))
            const.REMOTEOBJECT.serialize(initiate_connection_socket)
            if PeerText(initiate_connection_socket).receive(cmpstring=const.SERVEROK):
                # logs.serverlog('::Connection accepted by server', 2)
                print('::Connection accepted by server')
                threading.Thread(target=getlistfrom, args=(initiate_connection_socket,)).start()
            else:
                recv_list_user = remote_peer.deserialize(initiate_connection_socket)
                # const.LISTOFPEERS.add(recv_list_user)
                initiate_connection_socket.close()
                initiate_connection_socket = socket.socket(const.IPVERSION, const.PROTOCOL)
                initiate_connection_socket.connect(recv_list_user.requri)
                PeerText(initiate_connection_socket, const.REQFORLIST).send()
                print(f"::Connecting to {initiate_connection_socket.getpeername()}, ...getting list")
                threading.Thread(target=getlistfrom, args=(initiate_connection_socket,)).start()
                if recv_list_user.status == 1:
                    pass
            return True
        except socket.error as exp:
            if callcount >= const.MAXCALLBACKS:
                asyncio.run(main.endsession(0,0))
            # logs.serverlog(f"::Connection failed, retrying...{exp}", 1)
            print(f"::Connection failed, retrying...{exp}")
            if exp.errno == 10056:
                return False
            time.sleep(5)
            callcount += 1


def endconnection():
    global Safe
    print('::Disconnecting from server')
    Safe.set()
    try:
        const.REMOTEOBJECT.status = 0
        EndSocket = socket.socket(const.IPVERSION, const.PROTOCOL)
        EndSocket.connect((const.SERVERIP, const.SERVERPORT))
        if const.REMOTEOBJECT.serialize(EndSocket):
            EndSocket.close() if EndSocket else None
        const.LISTOFPEERS.clear()
        Safe = threading.Event()
    except Exception as exp:
        # serverlog(f'::Failed disconnecting from server{exp}', 4)
        print(f'::Failed closing server{exp}')

