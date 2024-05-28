from ..core import *
from ..avails import useables as use
from ..avails.remotepeer import RemotePeer

from ..avails.constants import NOMAD_FLAG  # control flag
from ..managers import directorymanager, filemanager
from ..managers.thread_manager import thread_handler, NOMAD
from ..webpage_handlers import handle_data
from ..avails.textobject import DataWeaver
from collections import defaultdict


class Nomad(object):
    # __annotations__ = {'address': tuple, '__control_flag': threading.Event, 'main_socket': socket.socket}
    # __slots__ = 'address', '__control_flag', 'main_socket','selector'

    def __init__(self, ip='localhost', port=8088):
        self.address = (ip, port)
        self.__control_flag = NOMAD_FLAG
        self.wake_read, self.wake_write = waker_flag()
        const.THIS_OBJECT = RemotePeer(const.USERNAME, ip, port, report=const.PORT_REQ, status=1)
        use.echo_print("::Initiating Nomad Object", self.address)
        self.main_socket = connect.Socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)
        self.currently_in_connection = defaultdict(int)

    def __resetSocket(self):
        self.main_socket = connect.Socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)
        self.main_socket.listen()

    def __acceptConnections(self):
        try:
            initial_conn, _ = self.main_socket.accept()
            use.echo_print(f"New connection from {_}")
            self.currently_in_connection[initial_conn] += 1
            # verify(initial_conn)
            th_controller = get_thread_controller(self.__control_flag, *waker_flag(), thread=None)
            thread = use.start_thread(self.connectNew, _args=(initial_conn, th_controller))  # name these threads .??
            thread_handler.save(th_controller._replace(thread=thread), NOMAD)
        except (socket.error, OSError) as e:
            error_log(f"Socket error: at commence/nomad.py exp:{e}")

    def initiate(self):
        self.main_socket.listen()
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print("::Listening for connections",self.main_socket)
        while True:
            reads, _, _ = select.select([self.main_socket, self.wake_read],[],[],)
            if self.safe_stop is True:
                break
            if self.main_socket not in reads:
                continue

            self.__acceptConnections()

    def connectNew(self, _conn, controller: ThController):
        _, check_read, writer, _, flag = controller
        while True:
            readable, _, _ = select.select([_conn, check_read], [], [], 592)
            if _conn not in readable or flag():
                use.echo_print(f"::Connection timed out : at {func_str(self.connectNew)}", _conn.getpeername())
                self.disconnectUser(_conn, writer)
                return
            try:
                if _conn.recv(1, socket.MSG_PEEK) == b'':
                    return
                _data = DataWeaver().receive(_conn)
            except socket.error as e:
                use.echo_print(
                    f"::Connection error: at {func_str(self.connectNew)} exp:{e}",
                    _conn.getpeername())
                return
            use.echo_print('data from peer :', _data)

            if _data.header == const.CMD_TEXT:
                asyncio.run(handle_data.feed_user_data_to_page(_data.content, _data.id))
                continue

            elif _data.header == const.CMD_RECV_FILE:
                use.start_thread(_target=filemanager.fileReceiver, _args=(_data,))

            elif _data.header == const.CMD_RECV_DIR:
                directorymanager.directoryReceiver(refer=_data)

            elif _data.header == const.CMD_CLOSING_HEADER:
                self.disconnectUser(_conn,writer)

        self.disconnectUser(_conn, writer)
        return

    def disconnectUser(self, _conn, writer):
        self.currently_in_connection[_conn] -= 1
        with _conn:
            DataWeaver(header=const.CMD_CLOSING_HEADER).send(_conn)
        writer()
        use.echo_print(f"::Closing connection at {func_str(Nomad.disconnectUser)}", _conn.getpeername())

    def end(self):
        self.__control_flag.set()
        self.wake_write()
        self.currently_in_connection.fromkeys(self.currently_in_connection, 0)
        self.main_socket.close() if self.main_socket else None
        use.echo_print("::Nomad Object Ended")

    @property
    def safe_stop(self) -> bool:
        return self.__control_flag.is_set()

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'

    def __del__(self):
        self.main_socket.close()
        self.wake_write()
