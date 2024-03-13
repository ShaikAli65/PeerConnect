import src.managers.directorymanager
from src.core import *
import src.avails.useables as use
from src.avails.remotepeer import RemotePeer
from src.webpage import handle_data
from src.managers import *
from src.avails.textobject import DataWeaver


class Nomad:
    currently_in_connection = {}

    def __init__(self, ip='localhost', port=8088):
        with const.LOCK_PRINT:
            time.sleep(const.anim_delay)
            print("::Initiating Nomad Object", ip, port)
        self.address = (ip, port)
        self.safe_stop = True
        const.THIS_OBJECT = RemotePeer(const.USERNAME, ip, port, report=const.PORT_REQ, status=1)
        self.main_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)

    def __resetSocket(self):
        self.main_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)
        self.main_socket.listen()

    def __acceptConnections(self):
        try:
            initiate_conn, _ = self.main_socket.accept()
            activity_log(f'New connection from {_[0]}:{_[1]}')
            use.echo_print(False, f"New connection from {_[0]}:{_[1]}")
            Nomad.currently_in_connection[initiate_conn] = True
            use.start_thread(connectNew, _args=(initiate_conn,))
        except (socket.error, OSError) as e:
            error_log(f"Socket error: at commence/nomad.py exp:{e}")

    def commence(self):
        self.main_socket.listen()
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print(True, "::Listening for connections at ", self.address)
        while self.safe_stop:
            readable, _, _ = select.select([self.main_socket], [], [], 0.001)
            if self.main_socket not in readable:
                continue
            if not isinstance(self.main_socket, socket.socket):
                self.__resetSocket()
            self.__acceptConnections()
        return

    def end(self):
        self.safe_stop = False
        if Nomad:
            Nomad.currently_in_connection = dict.fromkeys(Nomad.currently_in_connection, False)
        self.main_socket.close() if self.main_socket else None
        use.echo_print(True, "::Nomad Object Ended")

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'


function_map = {
    const.CMD_CLOSING_HEADER: lambda connection_socket: disconnectUser(connection_socket),
    const.CMD_RECV_DIR: lambda connection_socket: "sent you a dir : " + src.managers.directorymanager.directoryReceiver(connection_socket),
    const.CMD_RECV_FILE: lambda connection_socket: "sent you a file : " + filemanager.fileReceiver(connection_socket),
    const.CMD_RECV_DIR_LITE: lambda connection_socket: "sent you a directory through lite : " + directorymanager.directory_receiver(connection_socket),
    const.CMD_TEXT:lambda data: data
}


def connectNew(_conn: socket.socket):
    while Nomad.currently_in_connection.get(_conn):
        readable, _, _ = select.select([_conn], [], [], 592)
        if _conn not in readable:
            use.echo_print(False, "::Connection timed out :", _conn.getpeername())
            disconnectUser(_conn)
            return
        try:
            if _conn.recv(1, socket.MSG_PEEK) == b'':
                return
            _data = DataWeaver().receive(_conn)
        except socket.error as e:
            use.echo_print(False, f"::Connection error: at {__name__}/{__file__} exp:{e}", _conn.getpeername())
            return
        use.echo_print(False, 'data from peer :', _data)

        if _data.header == const.CMD_TEXT:
            asyncio.run(handle_data.feed_user_data_to_page(_data.content, _data.id))
            continue

        elif _data.header == const.CMD_RECV_FILE:
            use.start_thread(_target=filemanager.fileReceiver, _args=(_data,))

        elif _data.header == const.CMD_RECV_DIR:
            src.managers.directorymanager.directoryReceiver(refer=_data)

        elif _data.header == const.CMD_CLOSING_HEADER:
            disconnectUser(_conn)

    disconnectUser(_conn)
    return


def disconnectUser(_conn):
    Nomad.currently_in_connection[_conn] = False
    try:
        with _conn:
            DataWeaver(header=const.CMD_CLOSING_HEADER).send(_conn)
        use.echo_print(False, "::Closing connection from disconnectUser() from core/nomad at line 153")
    except socket.error:
        return
