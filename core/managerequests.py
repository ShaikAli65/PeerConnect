from avails import remotepeer
from core import *
import select

from webpage import handle

safe_stop = threading.Event()


def send_list(_conn: socket.socket):
    for _nomad in const.LIST_OF_PEERS.values():
        if not safe_stop.is_set():
            return
        if _nomad.status == 1:
            try:
                _nomad.serialize(_conn)
            except socket.error as e:
                errorlog(f"::Exception while giving list of users at manage requests/send_list, exp : {e}")
                print(f"::Exception while giving list of users: {e}")
                continue
    return


def initiate():
    global safe_stop
    safe_stop.set()
    control_sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
    control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    control_sock.bind(const.REMOTE_OBJECT.req_uri)
    control_sock.listen()
    const.HANDLE_CALL.wait()
    control_user_management(control_sock)
    return


def control_user_management(_control_sock: socket.socket):
    while safe_stop.is_set():
        readable, _, _ = select.select([_control_sock], [], [], 0.001)
        if _control_sock not in readable:
            continue

        try:
            initiate_conn, _ = _control_sock.accept()
            activitylog(f"New connection from {_[0]}:{_[1]}")
            print(f"New connection from {_[0]}:{_[1]} at control_user_management")
            threading.Thread(target=control_new_user, args=(initiate_conn,)).start()
        except (socket.error, OSError) as e:
            errorlog(f"Socket error at manage requests/control_user_management: {e}")
    return


def control_new_user(_conn: socket.socket):
    while safe_stop:
        readable, _, _ = select.select([_conn], [], [], 0.001)
        if _conn not in readable:
            continue
        try:
            data = PeerText(_conn)
            data.receive()
            if data.raw_text == const.REQ_FOR_LIST:
                PeerText(_conn, const.SERVER_OK).send()
                send_list(_conn)
                _conn.close()
                return
            elif data.raw_text == const.CMD_NOTIFY_USER:
                notify_user_connection(remotepeer.deserialize(_conn))
                _conn.close()
                return
        except (socket.error, OSError) as e:
            errorlog(f"Socket error at manage requests/control_new_user exp:{e}")
            _conn.close()
            return
    return


def notify_user_connection(_remote_peer: remotepeer):
    try:
        if not _remote_peer:
            return
        _remote_peer.status = 1
        handle.feed_server_data(_remote_peer)
        return None
    except Exception as e:
        errorlog(f"Error sending data at manager_requests.py/notify_user_connection exp :  {e}")
        return None
    pass


def notify_users():
    for peer in const.LIST_OF_PEERS.values():
        if not peer:
            continue
        try:
            notify_soc = socket.socket(const.IP_VERSION, const.PROTOCOL)
            notify_soc.connect(peer.req_uri)
            PeerText(notify_soc, const.CMD_NOTIFY_USER).send()
            const.REMOTE_OBJECT.serialize(notify_soc)
            notify_soc.close()
        except socket.error as e:
            errorlog(f"Error sending data at manager_requests.py/notify_users exp :  {e}")
    return None
