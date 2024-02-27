import timeit

from core import *
from avails.textobject import PeerText
import avails.useables as use
from avails.remotepeer import RemotePeer
from webpage import handle
from managers import *


class Nomad:
    currently_in_connection = {}
    LOOP_FLAG = True

    def __init__(self, ip='localhost', port=8088):
        with const.PRINT_LOCK:
            time.sleep(const.anim_delay)
            print("::Initiating Nomad Object", ip, port)
        self.address = (ip, port)
        self.safe_stop = True
        const.REMOTE_OBJECT = RemotePeer(const.USERNAME, ip, port, report=const.REQ_PORT, status=1)
        self.main_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)

    def commence(self):
        self.main_socket.listen()
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print(True, "::Listening for connections at ", self.address)
        while self.safe_stop:
            readable, _, _ = select.select([self.main_socket], [], [], 0.001)
            if self.main_socket not in readable:
                continue
            if not isinstance(self.main_socket, socket.socket):
                self.main_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
                self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.main_socket.bind(self.address)
                self.main_socket.listen()
            try:
                initiate_conn, _ = self.main_socket.accept()
                activity_log(f'New connection from {_[0]}:{_[1]}')
                with const.PRINT_LOCK:
                    print(f"New connection from {_[0]}:{_[1]}")
                Nomad.currently_in_connection[initiate_conn] = True
                use.start_thread(connectNew, args=(initiate_conn,))
            except (socket.error, OSError) as e:
                error_log(f"Socket error: {e}")

        return

    def end(self):
        self.safe_stop = False
        if Nomad:
            Nomad.currently_in_connection = dict.fromkeys(Nomad.currently_in_connection, False)
        self.main_socket.close() if self.main_socket else None
        use.echo_print(True, "::Nomad Object Ended")

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'

    def __del__(self):
        try:
            self.end()
        except Exception as exp:
            return exp


def send(_to_user_soc: socket.socket, _data: str):
    try:
        return PeerText(_to_user_soc, _data).send()
    except socket.error as err:
        with const.PRINT_LOCK:
            print(f"Error in sending data retrying... {err}")

    return False


def connectNew(_conn: socket.socket):
    while Nomad.currently_in_connection.get(_conn):
        readable, _, _ = select.select([_conn], [], [], 0.001)
        if _conn not in readable:
            continue
        connectNew_data = PeerText(_conn)
        connectNew_data.receive()
        if connectNew_data.compare(b"") and _conn.recv(1, socket.MSG_PEEK) == b"":
            _conn.close() if _conn else None
            return
        with const.PRINT_LOCK:
            print('data from peer :', connectNew_data)
        if connectNew_data.compare(const.CMD_CLOSING_HEADER):
            disconnect_user(_conn)
            return True
        elif connectNew_data.compare(const.CMD_RECV_FILE):

            # threading.Thread(target=filemanager.file_reciever,args=(_conn,)).start()
            filename = ""

            def wrapper():
                nonlocal filename
                filename = filemanager.file_reciever(_conn)

            recieve_time = timeit.timeit(wrapper, number=1)
            asyncio.run(handle.feed_user_data_to_page("sent u a file : " + filename, _conn.getpeername()[0]))

            print("::recieving time: ", recieve_time)
            disconnect_user(_conn)
            return True
        elif connectNew_data.compare(const.CMD_RECV_DIR):
            dir_name = filemanager.directory_reciever(_conn)
            asyncio.run(handle.feed_user_data_to_page("sent u a directory : " + dir_name, _conn.getpeername()[0]))
        elif connectNew_data.compare(const.CMD_RECV_DIR_LITE):
            dir_name = directorymanager.directory_reciever(_conn)
            asyncio.run(handle.feed_user_data_to_page("sent u a directory through lite : " + dir_name, _conn.getpeername()[0]))
        elif connectNew_data.raw_text:
            asyncio.run(handle.feed_user_data_to_page(connectNew_data.decode(), _conn.getpeername()[0]))
    return True


def disconnect_user(_conn):
    _conn.close()
    print("::Closing connection from disconnect_user() from core/nomad at line 153")
