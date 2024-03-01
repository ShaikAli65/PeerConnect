import queue
from collections import deque
from avails import remotepeer
from core import *
from avails import useables as use
from webpage import handle
from avails.textobject import PeerText

safe_stop = threading.Event()


def send_list(_conn: socket.socket) -> Union[None, bool]:
    with const.LOCK_LIST_PEERS:
        peer_list = const.LIST_OF_PEERS.copy()
    byte_length = struct.pack('!Q', len(const.LIST_OF_PEERS))
    _conn.sendall(byte_length)
    error_call = 0
    for _nomad in peer_list.values():
        if not safe_stop.is_set():
            return
        if not _nomad.status == 1:
            continue
        try:
            _nomad.serialize(_conn)
        except socket.error as e:
            error_log(f"::Exception while giving list of users at manage requests/send_list, exp : {e}")
            error_call += 1
            with const.LOCK_PRINT:
                print(
                    f"::Exception while giving list of users to {_conn.getpeername()} at manage_requests.py/send_list \n-exp : {e}")
            if error_call > const.MAX_CALL_BACKS:
                return False
    return


def add_peer_accordingly(_peer: remotepeer.RemotePeer, include_ping=False):
    if _peer.status == 1:
        with const.LOCK_LIST_PEERS:
            const.LIST_OF_PEERS[_peer.id] = _peer
        use.echo_print(False, f"::added {_peer.uri} {_peer.username} to list of peers")
    else:
        if include_ping:
            if ping_user(_peer):
                return
        with const.LOCK_LIST_PEERS:
            const.LIST_OF_PEERS.pop(_peer.id, None)
            _peer.status = 0
        use.echo_print(False, f"::removed {_peer.uri} {_peer.username} from list of peers")
    asyncio.run(handle.feed_server_data_to_page(_peer))
    return True


def initiate():
    global safe_stop
    safe_stop.set()
    control_sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
    control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    control_sock.bind(const.REMOTE_OBJECT.req_uri)
    control_sock.listen()
    use.echo_print(True, "::Requests bind success full at ", const.REMOTE_OBJECT.req_uri)
    control_user_manager(control_sock)
    return


def control_user_manager(_control_sock: socket.socket):
    use.echo_print(True, "::Listening for requests at ", _control_sock.getsockname())
    while safe_stop.is_set():
        readable, _, _ = select.select([_control_sock], [], [], 0.001)
        if _control_sock not in readable:
            continue
        try:
            initiate_conn, _ = _control_sock.accept()
            use.start_thread(_target=control_connection, _args=(initiate_conn,))
        except (socket.error, OSError) as e:
            error_log(f"Error at manage requests/control_user_management exp: {e}")
    return


def sync_users_with_server(_conn: socket.socket):
    with _conn:
        raw_data = _conn.recv(8)
        if not (diff_length := struct.unpack('!Q', raw_data)[0]):
            return
        for _ in range(diff_length):
            try:
                notify_user_connection(_conn,True)
            except Exception as e:
                error_log(f"Error syncing list at manager_requests.py/sync_list exp :  {e}")
    return


def notify_user_connection(_conn_socket: socket.socket,ping_again=False):
    try:
        new_peer_object: remotepeer.RemotePeer = remotepeer.deserialize(_conn_socket)
        if not new_peer_object:
            return False
    except Exception as e:
        error_log(f"Error sending data at manager_requests.py/notify_user_connection exp :  {e}")
        return None
    return add_peer_accordingly(new_peer_object,include_ping=ping_again)


function_map = {
    const.REQ_FOR_LIST: send_list,
    const.I_AM_ACTIVE: notify_user_connection,
    const.SERVER_PING: sync_users_with_server,
    const.ACTIVE_PING: None,
    const.LIST_SYNC: None
}


def control_connection(_conn: socket.socket):
    while safe_stop.is_set():
        try:
            readable, _, _ = select.select([_conn], [], [], 0.001)
        except OSError:
            return
        if _conn in readable:
            try:
                data = PeerText(_conn)
                data.receive()
                # print(f"::Received {data.raw_text} from {_conn.getpeername()}")
            except (socket.error, OSError) as e:
                error_log(f"Socket error at manage requests/control_connection exp:{e}")
                return
            function_map[data.raw_text](_conn) if function_map.get(data.raw_text) else None
            return


def ping_user(remote_peer: remotepeer.RemotePeer):
    try:
        with socket.socket(const.IP_VERSION, const.PROTOCOL) as _conn:
            _conn.settimeout(1)
            _conn.connect(remote_peer.req_uri)
            return True if PeerText(_conn, const.ACTIVE_PING, byteable=False).send() else False
    except socket.error as e:
        error_log(f"Error pinging user at requests_handler.py/ping_user exp :  {e}")
        return False


def signal_active_status(queue_in: queue.Queue[remotepeer.RemotePeer]):
    while safe_stop.is_set() and (not queue_in.empty()):
        peer_object = queue_in.get()
        try:
            with socket.socket(const.IP_VERSION, const.PROTOCOL) as _conn:
                _conn.connect(peer_object.req_uri)
                PeerText(_conn, const.I_AM_ACTIVE, byteable=False).send()
                const.REMOTE_OBJECT.serialize(_conn)
        except socket.error:
            use.echo_print(False, f"Error sending active status at manager_requests.py/signal_active_status")
        add_peer_accordingly(peer_object)


def notify_users():
    const.LOCK_LIST_PEERS.acquire()
    const.REMOTE_OBJECT.status = 0
    for peer in const.LIST_OF_PEERS.values():
        if not peer:
            continue
        try:
            with socket.socket(const.IP_VERSION, const.PROTOCOL) as notify_soc:
                notify_soc.settimeout(0.3)
                notify_soc.connect(peer.req_uri)
                PeerText(notify_soc, const.I_AM_ACTIVE, byteable=False).send()
                const.REMOTE_OBJECT.serialize(notify_soc)
        except socket.error as e:
            error_log(f"Error sending leaving status at manager_requests.py/notify_users exp :  {e}")
    return None


def sync_list() -> None:
    with const.LOCK_LIST_PEERS:
        list_copy = deque(const.LIST_OF_PEERS.values())
    while list_copy:
        if safe_stop.is_set():
            return
        peer_obj = list_copy.popleft()
        if not ping_user(peer_obj):
            peer_obj.status = 0
            add_peer_accordingly(peer_obj)
            continue
    return


def end_requests_connection():
    global safe_stop
    safe_stop.set()
    const.REMOTE_OBJECT.status = 0
    notify_users()
    print("::Requests connections ended")
    return None
