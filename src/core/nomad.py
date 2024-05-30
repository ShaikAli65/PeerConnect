from ..core import *
from ..avails import useables as use
from ..avails.remotepeer import RemotePeer

from ..avails.constants import NOMAD_FLAG  # control flag
from ..managers import directorymanager, filemanager
from ..managers.thread_manager import thread_handler, NOMADS
from ..webpage_handlers import handle_data
from ..avails.textobject import DataWeaver
from collections import defaultdict


class Nomad(object):
    # __annotations__ = {'address': tuple, '__control_flag': threading.Event, 'main_socket': socket.socket}
    # __slots__ = 'address', '__control_flag', 'main_socket','selector'

    def __init__(self, ip='localhost', port=8088):
        self.address = (ip, port)
        self.__control_flag = NOMAD_FLAG
        self.controller = ThreadController(None)
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

    def verify(self, _conn):
        # DataWeaver(header=const.CMD_TEXT, content="Hello").send(_conn)
        pass

    def __acceptConnections(self):
        try:
            initial_conn, _ = self.main_socket.accept()
            use.echo_print(f"New connection from {_}")
            if self.currently_in_connection[initial_conn] > 4:
                initial_conn.close()
                return

            # verify(initial_conn)

            self.currently_in_connection[initial_conn] += 1

            th_controller = ThreadController(self.__control_flag, None)
            thread = use.start_thread(self.connectNew, _args=(initial_conn,))  # name these threads .??
            th_controller.thread = thread

            thread_handler.register(th_controller, NOMADS)
        except (socket.error, OSError) as e:
            error_log(f"Socket error: at commence/nomad.py exp:{e}")

    def initiate(self):
        self.main_socket.listen()
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print("::Listening for connections", self.main_socket)
        while True:
            reads, _, _ = select.select([self.main_socket, self.controller.reader], [], [])
            if self.controller.to_stop is True:
                break
            if self.main_socket not in reads:
                continue

            self.__acceptConnections()

    def connectNew(self, _conn):
        while True:
            readable, _, _ = select.select([_conn, self.controller.reader], [], [], 500)
            if self.controller.to_stop is True:
                _conn.close()
                return
            if _conn not in readable:
                use.echo_print(f"::Connection timed out : at {func_str(self.connectNew)}", _conn.getpeername())
                self.disconnectUser(_conn, self.controller)
                return
            try:
                if _conn.recv(1, socket.MSG_PEEK) == b'':
                    use.echo_print(f"::Connection closed by peer at {func_str(self.connectNew)}", _conn.getpeername())
                    return
                _data = DataWeaver().receive(_conn)
            except socket.error as e:
                use.echo_print(
                    f"::Connection error: at {func_str(self.connectNew)} exp:{e}",
                    _conn.getpeername())
                _conn.close()
                return
            use.echo_print('data from peer :\n', _data)

            if _data.header == const.CMD_TEXT:
                asyncio.run(handle_data.feed_user_data_to_page(_data.content, _data.id))
                continue

            elif _data.header == const.CMD_RECV_FILE:
                use.start_thread(_target=filemanager.fileReceiver, _args=(_data,))

            elif _data.header == const.CMD_RECV_DIR:
                directorymanager.directoryReceiver(refer=_data)

            elif _data.header == const.CMD_CLOSING_HEADER:
                self.disconnectUser(_conn, self.controller)

        return

    def disconnectUser(self, _conn, _controller):
        self.currently_in_connection[_conn.getpeername()[0]] -= 1
        with _conn:
            DataWeaver(header=const.CMD_CLOSING_HEADER).send(_conn)
            use.echo_print(f"::Closing connection at {func_str(Nomad.disconnectUser)}", _conn.getpeername())

        _controller.stop()
        thread_handler.delete(_controller, NOMADS)

    def end(self):
        self.controller()
        self.currently_in_connection.fromkeys(self.currently_in_connection, 0)
        self.main_socket.close() if self.main_socket else None
        use.echo_print("::Nomad Object Ended")

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'

    def __del__(self):
        self.main_socket.close()
        self.controller()
        # for sock in self.currently_in_connection.keys():
        # sock.close()
