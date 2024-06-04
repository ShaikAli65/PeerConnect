import queue

import src.avails.useables as use
from src.avails.useables import REQ_URI_CONNECT

from src.core import *
from src.core import requests_handler
from src.avails.textobject import SimplePeerText
from src.avails.remotepeer import RemotePeer
from src.avails.constants import CONNECT_SERVER_FLAG


error_calls = 0
connection_status = False
_controller = ThreadActuator(None, control_flag=CONNECT_SERVER_FLAG)
TIMEOUT = 50  # sec


def get_initial_list(no_of_users, initiate_socket):
    global error_calls
    ping_queue = queue.Queue()
    for _ in range(no_of_users):
        try:
            _nomad = RemotePeer.deserialize(initiate_socket)
            ping_queue.put(_nomad)
            requests_handler.signal_status(ping_queue,)
            # use.echo_print(f"::User received from server : {_nomad}")
            server_log(f"::User received from server : {_nomad!r}", 2)
        except socket.error as e:
            error_log('::Exception while receiving list of users at connect server.py/get_initial_list, exp:' + str(e))
            if not e.errno == 10054:
                continue

            end_connection_with_server()
            if len(peer_list) > 0:
                server_log(f"::Server disconnected received some users retrying ...", 4)
                list_error_handler()
            return False
    return True


def list_error_handler():
    req_peer = next(peer_list)
    conn = use.create_conn_to_peer(_peer_obj=req_peer, to_which=REQ_URI_CONNECT)
    with conn:
        SimplePeerText(text=const.REQ_FOR_LIST,refer_sock=conn).send()
        select.select([conn, _controller], [], [], 100)
        list_len = struct.unpack('!Q',conn.recv(8))[0]
        get_initial_list(list_len, conn)


def get_list_from(initiate_socket):
    const.PAGE_HANDLE_CALL.wait()
    global error_calls

    select.select([initiate_socket, _controller], [], [], 100)
    if _controller.to_stop is True:
        return False

    with initiate_socket:
        raw_length = initiate_socket.recv(8)
        length = struct.unpack('!Q', raw_length)[0]  # number of users
        return get_initial_list(length, initiate_socket)


def list_from_forward_control(list_owner: RemotePeer):
    # socket.create_connection()
    with use.create_conn_to_peer(list_owner, to_which=REQ_URI_CONNECT) as list_connection_socket:
        if SimplePeerText(list_connection_socket, const.REQ_FOR_LIST, controller=_controller).send():
            get_list_from(list_connection_socket)


def initiate_connection():
    global error_calls, connection_status

    use.echo_print("::Connecting to server")
    server_connection = setup_server_connection()
    if server_connection is None:
        return False if (const.END_OR_NOT is True) else None

    text = SimplePeerText(server_connection, controller=_controller)
    if text.receive(cmp_string=const.SERVER_OK):
        use.echo_print('\n::Connection accepted by server')
        get_list_from(server_connection)
    elif text.compare(const.REDIRECT):
        # server may send a peer's details to get list from
        recv_list_user = RemotePeer.deserialize(server_connection)
        use.echo_print('::Connection redirected by server to : ', recv_list_user.req_uri)
        list_from_forward_control(recv_list_user)
    else:
        return None
    connection_status = True
    return True


def setup_server_connection():
    retry_count = 0
    while _controller.to_stop is False:
        try:
            _address = (const.SERVER_IP, const.PORT_SERVER)
            server_connection = connect.create_connection(_address, timeout=const.SERVER_TIMEOUT)
            break
        except (ConnectionRefusedError, TimeoutError, ConnectionError):
            if retry_count >= const.MAX_CALL_BACKS:
                use.echo_print("\n::Ending program server refused connection")
                return None
            try:
                retry_count += 1
                print(f"\r::Connection refused by server, {f'retrying... {retry_count}' if _controller.to_stop is False else 'returning'}", end='')
            except KeyboardInterrupt:
                return

    else:
        return None
    try:
        const.THIS_OBJECT.serialize(server_connection)
    except (socket.error,OSError):
        server_connection.close()
        return
    return server_connection


def end_connection_with_server():
    _controller.signal_stopping()
    print("::Cleared server flag")
    try:
        const.THIS_OBJECT.status = 0
        if connection_status is False:
            return True
        with connect.create_connection((const.SERVER_IP, const.PORT_SERVER), timeout=const.SERVER_TIMEOUT) as end_socket:
            const.THIS_OBJECT.serialize(end_socket)
        print("::sent leaving status to server")
        return True
    except Exception as exp:
        server_log(f'::Failed disconnecting from server at {__name__}/{__file__}, exp : {exp}', 4)
        return False
