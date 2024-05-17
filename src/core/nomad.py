from src.core import *
from src.avails import useables as use
from src.avails.remotepeer import RemotePeer
import src.core.receivers as receivers

NOMAD_FLAG = 1  # control flag index


class Nomad:
    __annotations__ = {'address': tuple, '__control_flag': threading.Event, 'main_socket': socket.socket}
    __slots__ = ['address', '__control_flag', 'main_socket']

    def __init__(self, ip='localhost', port=8088):
        self.address = (ip, port)
        self.__control_flag = const.CONTROL_FLAG[NOMAD_FLAG]
        const.THIS_OBJECT = RemotePeer(const.USERNAME, ip, port, report=const.PORT_REQ, status=1)
        use.echo_print("::Initiating Nomad Object", self.address)
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
            activity_log(f'New connection from {_}')
            use.echo_print(f"New connection from {_}")
            use.start_thread(receivers.connectNew, _args=(initiate_conn,))
        except (socket.error, OSError) as e:
            error_log(f"Socket error: at commence/nomad.py exp:{e}")

    def commence(self):
        self.main_socket.listen()
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print("::Listening for connections at ", self.address)

        while self.safe_stop:
            readable, _, _ = select.select([self.main_socket], [], [], 0.001)
            if self.main_socket not in readable:
                continue

            if not isinstance(self.main_socket, socket.socket):
                self.__resetSocket()
            self.__acceptConnections()
        return

    def end(self):
        const.CONTROL_FLAG[NOMAD_FLAG].clear()
        receivers.currently_in_connection.fromkeys(receivers.currently_in_connection, False)
        self.main_socket.close() if self.main_socket else None
        use.echo_print("::Nomad Object Ended")

    @property
    def safe_stop(self) -> bool:
        return self.__control_flag.is_set()

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'
