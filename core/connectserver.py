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
    initial_list_peer = const.LIST_OF_PEERS
    count_of_user = 0
    if no_of_users == 0:
        return False
    for _ in range(no_of_users):

        try:
            readable, _, _ = select.select([initiate_socket], [], [], 0.001)
            if initiate_socket not in readable:
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
            errorlog('::Exception while receiving list of users at connect server.py/initial_list, exp:' + str(e))
            if e.errno == 10054:
                time.sleep(5)
                end_connection()
                serverlog(f"::Server disconnected retry count :{_}", 4)
                initiate_connection()
                return False

    return True


def get_list_from(initiate_socket):
    const.HANDLE_CALL.wait()
    global Safe, ErrorCalls
    raw_length = 0
    for _ in range(const.MAX_CALL_BACKS):
        try:
            readable, _, _ = select.select([initiate_socket], [], [], 0.001)
            if initiate_socket not in readable:
                continue
            raw_length = initiate_socket.recv(8)
            break
        except socket.error as e:
            errorlog('::Exception while receiving list of users at connect server.py/get_list_from ' + str(e))
            print(f"::Exception while receiving list of users: retrying... {e}")
            continue

    return initial_list(struct.unpack('!Q', raw_length)[0], initiate_socket)


def initiate_connection():
    global Safe, ErrorCalls
    call_count = 0
    while not Safe.is_set():

        try:
            initiate_connection_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
            initiate_connection_socket.connect((const.SERVER_IP, const.SERVER_PORT))
            const.REMOTE_OBJECT.serialize(initiate_connection_socket)
            if PeerText(initiate_connection_socket).receive(cmpstring=const.SERVER_OK):
                serverlog('::Connection accepted by server connect', 2)
                print('::Connection accepted by server')
                threading.Thread(target=get_list_from, args=(initiate_connection_socket,)).start()
            else:
                recv_list_user = remote_peer.deserialize(initiate_connection_socket)
                # const.LIST_OF_PEERS.add(recv_list_user)
                initiate_connection_socket.close()
                initiate_connection_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
                initiate_connection_socket.connect(recv_list_user.req_uri)
                PeerText(initiate_connection_socket, const.REQ_FOR_LIST).send()
                print(f"::Connecting to {initiate_connection_socket.getpeername()}, ...getting list")
                threading.Thread(target=get_list_from, args=(initiate_connection_socket,)).start()
                if recv_list_user.status == 1:
                    pass
            return True
        except socket.error as exp:
            if call_count >= const.MAX_CALL_BACKS:
                asyncio.run(main._(0, 0))
            serverlog(f'::Connection failed, retrying... at server.py/initiate_connection, exp : {exp}', 1)
            if exp.errno == 10056:
                return False
            time.sleep(5)
            call_count += 1


def end_connection():
    global Safe
    print("::Disconnecting from server")
    Safe.set()
    try:
        const.REMOTE_OBJECT.status = 0
        EndSocket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        EndSocket.connect((const.SERVER_IP, const.SERVER_PORT))
        if const.REMOTE_OBJECT.serialize(EndSocket):
            EndSocket.close() if EndSocket else None
        const.LIST_OF_PEERS.clear()
        Safe = threading.Event()
        print("::Disconnected from server")
    except Exception as exp:
        serverlog(f'::Failed disconnecting from server at server.py/end_connection, exp : {exp}', 4)
        print(f'::Failed closing server{exp}')

