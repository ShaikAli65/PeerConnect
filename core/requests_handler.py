import queue

from avails import remotepeer
from core import *
from avails import useables as use
from webpage import handle
from avails.textobject import PeerText

safe_stop = threading.Event()


def send_list(_conn: socket.socket):
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
                print(f"::Exception while giving list of users to {_conn.getpeername()} at manage_requests.py/send_list \n-exp : {e}")
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


def sync_users(_conn: socket.socket):
    with const.LOCK_LIST_PEERS:
        use.echo_print(False, "::Syncing list with server",const.LIST_OF_PEERS)
    with _conn:
        raw_data = _conn.recv(4)
        diff_length = struct.unpack('!I', raw_data)[0]
        for _ in range(diff_length):
            try:
                notify_user_connection(_conn)
            except Exception as e:
                error_log(f"Error syncing list at manager_requests.py/sync_list exp :  {e}")
    return


def control_connection(_conn: socket.socket):
    while safe_stop.is_set():
        try:
            readable, _, _ = select.select([_conn], [], [], 0.001)
        except OSError as e:
            return
        if _conn in readable:
            try:
                data = PeerText(_conn)
                data.receive()
            except (socket.error, OSError) as e:
                error_log(f"Socket error at manage requests/control_connection exp:{e}")
                return
            if data.compare(const.REQ_FOR_LIST):
                send_list(_conn)
            elif data.compare(const.I_AM_ACTIVE):
                notify_user_connection(_conn)
            elif data.compare(const.SERVER_PING):
                sync_users(_conn)
            elif data.compare(const.ACTIVE_PING):
                pass
            elif data.compare(const.LIST_SYNC):
                pass
            return


def notify_user_connection(_conn_socket: socket.socket):
    try:
        new_peer_object: remotepeer.RemotePeer = remotepeer.deserialize(_conn_socket)
        if not new_peer_object:
            return
        with const.LOCK_LIST_PEERS:
            if new_peer_object.status == 1:
                const.LIST_OF_PEERS[new_peer_object.uri[0]] = new_peer_object
                use.echo_print(False, f"{new_peer_object} said i came ...")
            else:
                const.LIST_OF_PEERS.pop(new_peer_object.uri[0], None)
                use.echo_print(False, f"{new_peer_object} said i am going ...")
        asyncio.run(handle.feed_server_data_to_page(new_peer_object))
        return None
    except Exception as e:
        error_log(f"Error sending data at manager_requests.py/notify_user_connection exp :  {e}")
        return None
    pass


def add_peer_accordingly(_peer: remotepeer.RemotePeer):
    if not _peer:
        return False
    with const.LOCK_LIST_PEERS:
        if _peer.status == 1:
            const.LIST_OF_PEERS[_peer.uri[0]] = _peer
        else:
            const.LIST_OF_PEERS.pop(_peer.uri[0], None)
    asyncio.run(handle.feed_server_data_to_page(_peer))
    return True


def signal_active_status(queue_in: queue.Queue[remotepeer.RemotePeer]):
    while safe_stop.is_set() and (not queue_in.empty()):
        peer_object = queue_in.get()
        try:
            with socket.socket(const.IP_VERSION, const.PROTOCOL) as _conn:
                _conn.settimeout(0.1)
                _conn.connect(peer_object.req_uri)
                PeerText(_conn, const.I_AM_ACTIVE, byteable=False).send()
                const.REMOTE_OBJECT.serialize(_conn)
        except socket.error as e:
            pass
        if add_peer_accordingly(peer_object):
            use.echo_print(False,f"user {peer_object.id} name {peer_object.username} added to list")
        else:
            use.echo_print(False,f"user {peer_object.id} name {peer_object.username} not added to list")
    return None


def notify_users():
    const.LOCK_LIST_PEERS.acquire()
    for peer in const.LIST_OF_PEERS.values():
        if not peer:
            continue
        try:
            with socket.socket(const.IP_VERSION, const.PROTOCOL) as notify_soc:
                notify_soc.connect(peer.req_uri)
                PeerText(notify_soc, const.I_AM_ACTIVE, byteable=False).send()
                const.REMOTE_OBJECT.status = 0
                const.REMOTE_OBJECT.serialize(notify_soc)
        except socket.error as e:
            error_log(f"Error sending leaving status at manager_requests.py/notify_users exp :  {e}")
    return None


def sync_list():
    with const.LOCK_LIST_PEERS:
        list_copy = const.LIST_OF_PEERS.copy()
    for peer_obj in list_copy.values():
        if not peer_obj:
            continue
        try:
            with socket.socket(const.IP_VERSION, const.PROTOCOL) as sever_conn:
                sever_conn.settimeout(0.3)
                sever_conn.connect(peer_obj.req_uri)
                PeerText(sever_conn, const.ACTIVE_PING,byteable=False).send()
        except socket.error as e:
            use.echo_print(False, f"Looks like the user is inactive {peer_obj.username}({peer_obj.uri}) at manager_requests.py/sync_list exp :  {e}")
            peer_obj.status = 0
            add_peer_accordingly(peer_obj)
            return None
    return None


def end_requests_connection():
    global safe_stop
    safe_stop.set()
    const.REMOTE_OBJECT.status = 0
    notify_users()
    print("::Requests connections ended")
    return None
