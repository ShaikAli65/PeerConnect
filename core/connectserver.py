import queue

from core import *
from core import requests_handler
from webpage import handle
from logs import *
from avails.textobject import PeerText
import avails.useables as use
import avails.remotepeer as remote_peer

End_Safe = threading.Event()
Error_Calls = 0


def initial_list(no_of_users: int, initiate_socket):
    global End_Safe, Error_Calls
    queue_lock = threading.Lock()
    ping_queue = queue.Queue()
    if no_of_users == 0:
        return None
    for i in range(no_of_users):
        try:
            readable, _, _ = select.select([initiate_socket], [], [], 0.001)
            if i % const.MAX_CALL_BACKS == 0:
                use.start_thread(_target=requests_handler.signal_active_status, _args=(ping_queue, queue_lock))
            if initiate_socket not in readable:
                continue
            _nomad:remote_peer.RemotePeer = remote_peer.deserialize(initiate_socket)
        except socket.error as e:
            error_log('::Exception while receiving list of users at connect server.py/initial_list, exp:' + str(e))
            if e.errno == 10054:
                end_connection_with_server()
                time.sleep(5)
                if not ping_queue.empty():
                    server_log(f"::Server disconnected recieved some users retrying ...", 4)
                    list_error_handler()
                return False
    if not ping_queue.empty():
        use.start_thread(_target=requests_handler.signal_active_status, _args=(ping_queue, queue_lock))
    initiate_socket.close()
    return True


def list_error_handler():
    pass


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
            use.echo_print(False,f"::Exception while receiving list of users: retrying... {e}")
            end_connection_with_server()
            initiate_connection()
        except Exception as e:
            print(f"::Exception fatal... exp:{e}")
            return False
    return initial_list(struct.unpack('!Q', raw_length)[0], initiate_socket)


def list_from_forward_control(list_owner_remote:remote_peer.RemotePeer):
    with const.LOCK_PRINT:
        print('::Connection redirected by server to : ', list_owner_remote.req_uri)
    # const.LIST_OF_PEERS.add(list_owner_remote)
    list_connection_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
    list_connection_socket.connect(list_owner_remote.req_uri)
    PeerText(list_connection_socket, const.REQ_FOR_LIST, byteable=False).send()
    print(f"::Connecting to {list_connection_socket.getpeername()}, ...getting list")
    use.start_thread(_target=get_list_from, _args=(list_connection_socket,))
    return True if list_connection_socket else False


def initiate_connection():
    global End_Safe, Error_Calls
    call_count = 0
    with const.LOCK_PRINT:
        print("::Connecting to server")
    while not End_Safe.is_set():
        try:
            server_connection_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
            server_connection_socket.connect((const.SERVER_IP, const.SERVER_PORT))
            const.REMOTE_OBJECT.serialize(server_connection_socket)

            if PeerText(server_connection_socket).receive(cmpstring=const.SERVER_OK):
                server_log('::Connection accepted by server connect', 2)
                with const.LOCK_PRINT:
                    print('::Connection accepted by server')
                use.start_thread(_target=get_list_from, _args=(server_connection_socket,))
            else:
                recv_list_user = remote_peer.deserialize(server_connection_socket)
                return list_from_forward_control(recv_list_user)
            return True
        except (ConnectionRefusedError, TimeoutError, ConnectionError):
            if call_count >= const.MAX_CALL_BACKS:
                time.sleep(const.anim_delay)
                print("\n::Ending program server refused connection")
                return False
            call_count += 1
            print(f"\r::Connection refused by server, retrying... {call_count}", end='')
            if End_Safe.is_set():
                return False
        except KeyboardInterrupt:
            return False
        except Exception as exp:
            server_log(f'::Connection fatal ... at server.py/initiate_connection, exp : {exp}', 4)
    return False


def end_connection_with_server():
    global End_Safe
    End_Safe.set()
    try:
        const.REMOTE_OBJECT.status = 0
        EndSocket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        with EndSocket:
            EndSocket.connect((const.SERVER_IP, const.SERVER_PORT))
            const.REMOTE_OBJECT.serialize(EndSocket)
        print("::sent leaving status to server")
        return True
    except Exception as exp:
        server_log(f'::Failed disconnecting from server at server.py/end_connection, exp : {exp}', 4)
        return False
