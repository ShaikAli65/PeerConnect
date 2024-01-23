from avails import textobject, remotepeer
from avails.textobject import PeerText
from core import *
import select

safestop = threading.Event()


def send_list(self, _conn):
    # for _nomad in const.LIST_OF_PEERS.values():
    #     if not Safe.is_set():
    #         return
    #     if _nomad.status == 1:
    #         try:
    #             _nomad.serialize(peer)
    #         except socket.error as e:
    #             # logs.errorlog(f"::Exception while giving list of users: {e}")
    #             print(f"::Exception while giving list of users: {e}")
    #             continue
    return


def control_user_management():
    control_sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
    control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # control_sock.bind(const.REMOTE_OBJECT.requri)
    # control_sock.listen()
    while safestop.is_set():
        readables, _, _ = select.select([control_sock], [], [], 0.001)
        if control_sock not in readables:
            continue
        try:
            initiate_conn, _ = control_sock.accept()
            # activitylog(f"New connection from {_[0]}:{_[1]}")
            print(f"New connection from {_[0]}:{_[1]} at control_user_management")
            threading.Thread(target=control_new_user, args=(initiate_conn,)).start()
        except (socket.error, OSError) as e:
            errorlog(f"Socket error: {e}")
    return


def control_new_user(_conn: socket.socket):
    while safestop:
        readables, _, _ = select.select([_conn], [], [], 0.001)
        if _conn not in readables:
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
                _remotepeerobj = remotepeer.deserialize(_conn)
                notify_user_connection(_remotepeerobj)
                _conn.close()
                return
        except (socket.error, OSError) as e:
            errorlog(f"Socket error: {e}")
            _conn.close()
            return
    return


def notify_user_connection(_remotepeerobj: remotepeer):
    try:
        if not _remotepeerobj:
            return
        _remotepeerobj.status = 1
        _remotepeerobj.serialize()
        # _remotepeerobj.send(const.CMDNOTIFYUSER)
    except Exception as e:
        # logs.errorlog(f"Error sending data: {e}")
        print(f"handle.py line 83 Error sending data: {e}")
        return
    pass
