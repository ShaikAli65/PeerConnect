import queue
from avails import remotepeer
from core import *

from webpage import handle

safe_stop = threading.Event()


def send_list(_conn: socket.socket):
    byte_length = struct.pack('!Q', len(const.LIST_OF_PEERS))
    _conn.sendall(byte_length)
    error_call = 0
    for _nomad in const.LIST_OF_PEERS.values():
        if not safe_stop.is_set():
            return
        if _nomad.status == 1:
            try:
                _nomad.serialize(_conn)
            except socket.error as e:
                error_log(f"::Exception while giving list of users at manage requests/send_list, exp : {e}")
                error_call += 1
                with const.PRINT_LOCK:
                    print(
                        f"::Exception while giving list of users to {_conn.getpeername()} at manage_requests.py/send_list \n-exp : {e}")
                if error_call > const.MAX_CALL_BACKS:
                    return False
    return


def initiate():
    global safe_stop
    safe_stop.set()
    control_sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
    control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    control_sock.bind(const.REMOTE_OBJECT.req_uri)
    control_sock.listen()
    use.echo_print(True,"::Requests bind success full at ", const.REMOTE_OBJECT.req_uri)
    const.PAGE_HANDLE_CALL.wait()
    control_user_manager(control_sock)
    return


def control_user_manager(_control_sock: socket.socket):
    use.echo_print(True,"::Listening for requests at ", _control_sock.getsockname())
    while safe_stop.is_set():
        readable, _, _ = select.select([_control_sock], [], [], 0.001)
        if _control_sock not in readable:
            continue
        try:
            initiate_conn, _ = _control_sock.accept()
            use.start_thread(_target=control_connected_user, args=(initiate_conn,))
        except (socket.error, OSError) as e:
            error_log(f"Error at manage requests/control_user_management exp: {e}")
    return


def control_connected_user(_conn: socket.socket):
    while safe_stop.is_set():
        readable, _, _ = select.select([_conn], [], [], 0.001)
        if _conn not in readable:
            continue
        with _conn:
            try:
                data = PeerText(_conn)
                data.receive()
                print(f"{_conn.getpeername()} said {data} at manage requests.py/control_connected_user")
                if data.compare(const.REQ_FOR_LIST):
                    send_list(_conn)
                    break
                elif data.compare(const.CMD_NOTIFY_USER):
                    notify_user_connection(_conn)
                    break
            except (socket.error, OSError) as e:
                error_log(f"Socket error at manage requests/control_new_user exp:{e}")
                return
    return


def notify_user_connection(_conn_socket:socket.socket):
    try:
        new_peer_object: remotepeer.RemotePeer = remotepeer.deserialize(_conn_socket)
        if not new_peer_object:
            return
        if new_peer_object.status == 1:
            const.LIST_OF_PEERS[new_peer_object.uri[0]] = new_peer_object
            use.echo_print(False,f"{new_peer_object} said i came ...")
        else:
            const.LIST_OF_PEERS.pop(new_peer_object.uri[0],None)
            use.echo_print(False,f"{new_peer_object} said i am going ...")
        asyncio.run(handle.feed_server_data_to_page(new_peer_object))
        return None
    except Exception as e:
        error_log(f"Error sending data at manager_requests.py/notify_user_connection exp :  {e}")
        return None
    pass


def signal_active_status(queue_in: queue.Queue,lock:threading.Lock):
    while safe_stop.is_set() and not queue_in.empty():
        with lock:
            _id = queue_in.get()
            print(f"::at signal_active_status with {_id} :",threading.get_native_id())
        try:
            with socket.socket(const.IP_VERSION, const.PROTOCOL)as  _conn:
                _conn.connect(const.LIST_OF_PEERS[_id].req_uri)
                PeerText(_conn, const.CMD_NOTIFY_USER,byteable=False).send()
                const.REMOTE_OBJECT.serialize(_conn)
        except socket.error as e:
            error_log(f"Error sending active status at manager_requests.py/signal_active_status exp :  {e}")
    return None


def notify_users():
    for peer in const.LIST_OF_PEERS.values():
        if not peer:
            continue
        try:
            with socket.socket(const.IP_VERSION, const.PROTOCOL) as notify_soc:
                notify_soc.connect(peer.req_uri)
                PeerText(notify_soc, const.CMD_NOTIFY_USER,byteable=False).send()
                const.REMOTE_OBJECT.status = 0
                const.REMOTE_OBJECT.serialize(notify_soc)
        except socket.error as e:
            error_log(f"Error sending leaving status at manager_requests.py/notify_users exp :  {e}")
    return None


def end_connection():
    global safe_stop
    safe_stop.set()
    const.REMOTE_OBJECT.status = 0
    notify_users()
    print("::Requests connections ended")
    return None
