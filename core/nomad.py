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
        with const.LOCK_PRINT:
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
                with const.LOCK_PRINT:
                    print(f"New connection from {_[0]}:{_[1]}")
                Nomad.currently_in_connection[initiate_conn] = True
                use.start_thread(connectNew, _args=(initiate_conn,))
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
        use.echo_print(False, f"Error in sending data retrying... {err}")

    return False


function_map = {
    const.CMD_CLOSING_HEADER: lambda x: disconnect_user(x),
    const.CMD_RECV_DIR: lambda x: "sent you a dir : " + filemanager.directory_reciever(x),
    const.CMD_RECV_FILE: lambda x: "sent you a file : " + filemanager.file_reciever(x),
    const.CMD_RECV_DIR_LITE: lambda x: "sent you a directory through lite : " + directorymanager.directory_reciever(x),
}


def connectNew(_conn: socket.socket):
    while Nomad.currently_in_connection.get(_conn):
        readable, _, _ = select.select([_conn], [], [], 592)
        if _conn not in readable:
            print("::Connection timed out :", _conn.getpeername())
            disconnect_user(_conn)
            return
        try:
            _data = PeerText(_conn)
            _data.receive()
        except socket.error:
            return
        if _data.compare(b"") and _conn.recv(1, socket.MSG_PEEK) == b"":
            _conn.close() if _conn else None
            return

        use.echo_print(False, print('data from peer :', _data))

        message = function_map.get(_data.raw_text, lambda x: _data.decode())(_conn)
        asyncio.run(handle.feed_user_data_to_page(message, _conn.getpeername()[0]))

    return True


def disconnect_user(_conn):
    PeerText(_conn, const.CMD_CLOSING_HEADER, byteable=False).send()
    _conn.close()
    use.echo_print(False, "::Closing connection from disconnect_user() from core/nomad at line 153")
