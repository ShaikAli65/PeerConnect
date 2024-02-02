import queue
import main
from core import *
from avails.textobject import PeerText
import avails.remotepeer as remote_peer
from core import managerequests
from webpage import handle
import core.managerequests
from logs import *

End_Safe = threading.Event()
Error_Calls = 0


def initial_list(no_of_users: int, initiate_socket):
    global End_Safe, Error_Calls
    initial_list_peer = const.LIST_OF_PEERS
    ping_queue = queue.Queue()
    queue_lock = threading.Lock()
    if no_of_users == 0:
        return None
    for i in range(no_of_users):

        try:
            readable, _, _ = select.select([initiate_socket], [], [], 0.001)
            if i % const.MAX_CALL_BACKS == 0:
                main.start_thread(_target=managerequests.signal_active_status, args=(ping_queue,queue_lock))
            if initiate_socket not in readable:
                continue
            _nomad:remote_peer.RemotePeer = remote_peer.deserialize(initiate_socket)
            if _nomad.status == 1:
                initial_list_peer[_nomad.id] = _nomad
                ping_queue.put(_nomad.id)
            asyncio.run(handle.feed_server_data(_nomad))
            print(f"user {_nomad.id} name {_nomad.uri} added to list")
        except socket.error as e:
            error_log('::Exception while receiving list of users at connect server.py/initial_list, exp:' + str(e))
            if e.errno == 10054:
                time.sleep(5)
                end_connection()
                server_log(f"::Server disconnected retry count :{_}", 4)
                initiate_connection()
                return False
    if not ping_queue.empty():
        main.start_thread(_target=managerequests.signal_active_status, args=(ping_queue,queue_lock))
    initiate_socket.close()
    return True


def get_list_from(initiate_socket: socket.socket):
    const.PAGE_HANDLE_CALL.wait()
    global End_Safe, Error_Calls
    raw_length = 0
    for _ in range(const.MAX_CALL_BACKS):
        try:
            readable, _, _ = select.select([initiate_socket], [], [], 0.001)
            if initiate_socket not in readable:
                continue
            raw_length = initiate_socket.recv(8)
            break
        except socket.error as e:
            error_log('::Exception while receiving list of users at connect server.py/get_list_from ' + str(e))
            print(f"::Exception while receiving list of users: retrying... {e}")
            continue
        except Exception as e:
            print(f"::Exception while receiving list of users: retrying... {e}")
            continue
    return initial_list(struct.unpack('!Q', raw_length)[0], initiate_socket)


def initiate_connection():
    global End_Safe, Error_Calls
    call_count = 0
    with const.PRINT_LOCK:
        print("::Connecting to server")
    while not End_Safe.is_set():

        try:
            server_connection_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
            server_connection_socket.connect((const.SERVER_IP, const.SERVER_PORT))
            const.REMOTE_OBJECT.serialize(server_connection_socket)

            if PeerText(server_connection_socket).receive(cmpstring=const.SERVER_OK):
                server_log('::Connection accepted by server connect', 2)
                with const.PRINT_LOCK:
                    print('::Connection accepted by server')
                main.start_thread(_target=get_list_from, args=(server_connection_socket,))
            else:
                recv_list_user = remote_peer.deserialize(server_connection_socket)
                with const.PRINT_LOCK:
                    print('::Connection redirected by server to : ', recv_list_user.req_uri)
                # const.LIST_OF_PEERS.add(recv_list_user)
                list_connection_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
                list_connection_socket.connect(recv_list_user.req_uri)
                PeerText(list_connection_socket, const.REQ_FOR_LIST,byteable=False).send()
                print(f"::Connecting to {list_connection_socket.getpeername()}, ...getting list")
                main.start_thread(_target=get_list_from, args=(list_connection_socket,))
                if recv_list_user.status == 1:
                    pass
            return True
        except (ConnectionRefusedError, TimeoutError, ConnectionError):
            if call_count >= const.MAX_CALL_BACKS:
                time.sleep(const.anim_delay)
                print("\n::Ending program server refused connection")
                return False
            call_count += 1
            print(f"\r::Connection refused by server, retrying... {call_count}", end='')
            # time.sleep(1)
        except Exception as exp:
            if call_count >= const.MAX_CALL_BACKS:  # or exp.errno == 10054:
                return False
            print(f"\r::Connection refused by server, retrying... {call_count}", end='')
            server_log(f'::Connection failed, retrying... at server.py/initiate_connection, exp : {exp}', 4)


def end_connection():
    global End_Safe
    with const.PRINT_LOCK:
        time.sleep(const.anim_delay)
        print("::Disconnecting from server")
    End_Safe.set()
    try:
        const.REMOTE_OBJECT.status = 0
        EndSocket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        EndSocket.connect((const.SERVER_IP, const.SERVER_PORT))
        if const.REMOTE_OBJECT.serialize(EndSocket):
            EndSocket.close() if EndSocket else None
        const.LIST_OF_PEERS.clear()
        End_Safe = threading.Event()
        print("::Disconnected from server")
    except Exception as exp:
        server_log(f'::Failed disconnecting from server at server.py/end_connection, exp : {exp}', 4)
