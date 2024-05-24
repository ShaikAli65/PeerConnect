from concurrent.futures import ThreadPoolExecutor

from src.avails.textobject import DataWeaver
from src.core import *
from src.avails import useables as use
from src.avails.remotepeer import RemotePeer
import src.core.receivers as receivers
from src.avails.constants import NOMAD_FLAG   # control flag
from src.managers import filemanager
from src.webpage_handlers import handle_data


class Nomad:
    # __annotations__ = {'address': tuple, '__control_flag': threading.Event, 'main_socket': socket.socket}
    # __slots__ = ('address', '__control_flag', 'main_socket','selector','currently_in_connection')

    def __init__(self, ip='localhost', port=8088):
        self.address = (ip, port)
        self.__control_flag = NOMAD_FLAG
        const.THIS_OBJECT = RemotePeer(const.USERNAME, ip, port, report=const.PORT_REQ, status=1)
        use.echo_print("::Initiating Nomad Object", self.address)
        self.main_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)
        self.selector = selectors.DefaultSelector()
        self.currently_in_connection = {}
        self.thread_pool = ThreadPoolExecutor()

    def __resetSocket(self):
        self.main_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)
        self.main_socket.listen()

    def __acceptConnection(self):
        try:
            _conn, _ = self.main_socket.accept()
            use.echo_print(f"New connection from {_}")
            self.selector.register(_conn, selectors.EVENT_READ, receivers.connectNew)
            self.currently_in_connection[_conn] = True
        except (socket.error, OSError) as e:
            error_log(f"Socket error: at commence/nomad.py exp:{e}")

    def commence(self):
        self.main_socket.listen()
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print("::Listening for connections at ", self.address)
        self.selector.register(self, selectors.EVENT_WRITE | selectors.EVENT_READ, self.__acceptConnection)
        while self.safe_stop:
            events = self.selector.select()
            for key, mask in events:
                self.thread_pool.submit(key.data, (key.fileobj,))

    def connectNew(self, _conn: socket.socket):
        try:
            if _conn.recv(1, socket.MSG_PEEK) == b'':
                return
            _data = DataWeaver().receive(_conn)
        except socket.error as e:
            use.echo_print(
                f"::Connection error: exp:{e}",
                _conn.getpeername())
            return
        use.echo_print('data from peer :', _data)
        # things to do with _data
        return

    def disconnectUser(self, _conn):
        self.currently_in_connection[_conn] = False
        self.selector.unregister(_conn)
        with _conn:
            DataWeaver(header=const.CMD_CLOSING_HEADER).send(_conn)
        _conn.close()

    def end(self):
        NOMAD_FLAG.clear()
        receivers.currently_in_connection.fromkeys(receivers.currently_in_connection, False)
        self.main_socket.close() if self.main_socket else None
        use.echo_print("::Nomad Object Ended")

    @property
    def safe_stop(self) -> bool:
        return self.__control_flag.is_set()

    def fileno(self):
        return self.main_socket.fileno()

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'
