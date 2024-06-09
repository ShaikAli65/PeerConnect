from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from collections import deque

import src.avails.connect
from src.avails.remotepeer import RemotePeer
from src.core import *
from src.avails import useables as use
from src.avails.connect import REQ_URI_CONNECT
from src.managers.thread_manager import thread_handler, REQUESTS
from src.webpage_handlers import handle_data
from src.avails.textobject import SimplePeerText
from src.core.senders import RecentConnections
from src.avails.constants import REQ_FLAG
from src.avails.container import SocketStore

_controller = ThreadActuator(None, control_flag=REQ_FLAG)
thread_handler.register_control(_controller, REQUESTS)
event_selector = selectors.DefaultSelector()
thread_pool = ThreadPoolExecutor(7, 'peer-connect-request_handler')
connection_count = 0

connections = SocketStore()  # storing socket references what if we miss any socket closure ;)


def send_list(_conn):
    with _conn:
        no_of_peers = struct.pack('!Q', len(peer_list))
        _conn.send(no_of_peers)
        error_call = 0
        for _nomad in peer_list.peers():
            if _controller.to_stop:
                return
            try:
                _nomad.send_serialized(_conn)
            except socket.error as e:
                if error_call := adjust_list_error(error_call, _conn, e) > const.MAX_CALL_BACKS:
                    return

    connections.remove_socket(_conn)


def adjust_list_error(error_call, _conn, err):
    error_log(f"::Exception while giving list of users at {__name__}/{__file__}, exp : {err}")
    error_call += 1
    use.echo_print(
        f"::Exception while giving list of users to {_conn.getpeername()} at {func_str(adjust_list_error)} \n-exp : {err}")


def add_peer_accordingly(_peer: RemotePeer, *, include_ping=False):
    if _peer.status == 1:
        peer_list.add_peer(_peer)
        use.echo_print(f"::added {_peer.uri} {_peer.username} to list of peers")
    else:
        if include_ping:
            if ping_user(_peer):
                return False

        _peer.status = 0
        peer_list.remove_peer(_peer.id)
        RecentConnections.force_remove(_peer.id)
        use.echo_print(f"::removed {_peer.uri}, {_peer.req_uri} {_peer.username} from list of peers")
    asyncio.run(handle_data.feed_user_status_to_page(_peer))
    return True


def initiate():
    _control_sock = connect.create_server(const.THIS_OBJECT.req_uri,family=const.IP_VERSION, backlog=3)
    event_selector.register(_controller, selectors.EVENT_READ)
    event_selector.register(_control_sock, selectors.EVENT_READ, control_connection)
    use.echo_print("::Listening for requests at ", _control_sock.getsockname())

    while True:
        events = event_selector.select()
        if _controller.to_stop:
            use.echo_print("::Requests connections ended")
            return
        try:
            for event, _ in events:
                func = event.data
                sock = event.fileobj
                func(sock)
        except (socket.error, OSError) as e:
            error_log(f"Error at manage {func_str(initiate)} exp: {e}")
            print("error at requests_handler",e)  # debug


def control_connection(_conn):
    connection, _ = _conn.accept()  # this should not be blocking, as it is returned by  select call
    use.echo_print("New Connection at requests", _)
    connections.add_socket(connection)
    event_selector.register(connection, selectors.EVENT_READ, resolve_data)


def notify_user_connection(conn_socket, ping_again=False):
    with conn_socket:
        try:
            new_peer_object = RemotePeer.deserialize(conn_socket)
            if not new_peer_object:
                return
        except Exception as e:
            error_log(f"Error at {func_str(notify_user_connection)} exp :  {e}")
            return
        connections.remove_socket(conn_socket)
        return add_peer_accordingly(new_peer_object, include_ping=ping_again)


function_map = {
    const.REQ_FOR_LIST: lambda x: thread_pool.submit(send_list, x),
    const.I_AM_ACTIVE: notify_user_connection,
    const.SERVER_PING: lambda x: thread_pool.submit(sync_users_with_server, x),
    const.ACTIVE_PING: lambda x: None,
    const.LIST_SYNC: lambda x: None,
}


def resolve_data(_conn):
    data = SimplePeerText(_conn, controller=_controller).receive()
    use.echo_print(f"::Received {data} from {_conn.getpeername()}")
    # except (socket.error, OSError) as e:
    #     error_log(f"Socket error at {func_str(controlconnection)} exp:{e} peer:{connection.getpeername()}")
    #     return

    function_map.get(data, lambda x: None)(_conn)
    event_selector.unregister(_conn)


def sync_users_with_server(_conn):
    with _conn:
        raw_data = _conn.recv(8)
        if not (diff_length := struct.unpack('!Q', raw_data)[0]):
            return
        for _ in range(diff_length):
            try:
                notify_user_connection(_conn, True)
            except Exception as e:
                error_log(
                    f"Error syncing list at {func_str(sync_users_with_server)} exp :  {e}")
    connections.remove_socket(_conn)


def ping_user(remote_peer: RemotePeer):
    try:
        with src.avails.connect.connect_to_peer(remote_peer, to_which=REQ_URI_CONNECT, timeout=5) as _conn:
            return SimplePeerText(_conn, const.ACTIVE_PING).send()
    except socket.error as e:
        error_log(f"Error pinging user at {func_str(ping_user)} exp :  {e}")
        return False


def signal_status(queue_in: Queue[RemotePeer]):
    while not (_controller.to_stop or queue_in.empty()):
        peer_object = queue_in.get()
        try:
            with src.avails.connect.connect_to_peer(peer_object, to_which=REQ_URI_CONNECT, timeout=5) as _conn:
                SimplePeerText(_conn, const.I_AM_ACTIVE).send(require_confirmation=False)
                const.THIS_OBJECT.send_serialized(_conn)
        except socket.error:
            use.echo_print(f"Error sending status({const.THIS_OBJECT.status}) at {func_str(signal_status)}", peer_object)
            peer_object.status = 0  # this makes that user as not active
        add_peer_accordingly(peer_object)


def sync_list():
    with const.LOCK_LIST_PEERS:
        list_copy = deque(peer_list.peers())
    while list_copy:
        if _controller.to_stop:
            return
        peer_obj = list_copy.popleft()
        if not ping_user(peer_obj):
            peer_obj.status = 0
            add_peer_accordingly(peer_obj)
            continue
    return


def notify_leaving_status_to_users():
    const.THIS_OBJECT.status = 0
    for peer in peer_list.peers():
        if not peer:
            continue
        # try:
        use.echo_print("::Notifying leaving ", peer.uri, peer.username)
        try:
            with src.avails.connect.connect_to_peer(peer, to_which=REQ_URI_CONNECT, timeout=5) as _conn:
                SimplePeerText(_conn, const.I_AM_ACTIVE).send(require_confirmation=False)
                const.THIS_OBJECT.send_serialized(_conn)
        except socket.error:
            use.echo_print(f"Error sending leaving status at {func_str(signal_status)}")


def end_requests_connection():
    notify_leaving_status_to_users()
    _controller.signal_stopping()
    const.THIS_OBJECT.status = 0
    connections.close_all()
