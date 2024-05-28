from src.core import *
from src.avails import useables as use
from src.avails.remotepeer import RemotePeer
import src.core.receivers as receivers

from src.avails.constants import NOMAD_FLAG  # control flag
from src.avails.waiters import waker_flag
from concurrent.futures import ThreadPoolExecutor


class Nomad:
    # __annotations__ = {'address': tuple, '__control_flag': threading.Event, 'main_socket': connect.socket}
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
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.wake_read, selectors.EVENT_READ)
        self.threads = ThreadPoolExecutor()

    def __resetSocket(self):
        self.main_socket = connect.Socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)
        self.main_socket.listen()

    def __acceptConnections(self):
        try:
            initiate_conn, _ = self.main_socket.accept()
            use.echo_print(f"New connection from {_}")

            use.start_thread(self.connectNew, _args=(initiate_conn,))
        except (socket.error, OSError) as e:
            error_log(f"Socket error: at commence/nomad.py exp:{e}")

    def commence(self):
        self.main_socket.listen()
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print("::Listening for connections at ", self.address)
        self.selector.register(self.main_socket, selectors.EVENT_READ)
        while True:
            reads,_,_ = select.select([self.main_socket,self.wake_read],[],[])
            if not self.safe_stop:
                break
            if self.main_socket not in reads:
                continue
            if not isinstance(self.main_socket, connect.Socket):
                self.__resetSocket()
            self.__acceptConnections()
        return

    def end(self):
        NOMAD_FLAG.clear()
        self.wake_write()
        self.main_socket.close() if self.main_socket else None
        use.echo_print("::Nomad Object Ended")

    @property
    def safe_stop(self) -> bool:
        return self.__control_flag.is_set()

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'
