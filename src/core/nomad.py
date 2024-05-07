from src.core import *
from src.avails import useables as use
from src.avails.remotepeer import RemotePeer
from src.core.receivers import connectNew


class Nomad:
    currently_in_connection = {}
    __annotations__ = {'address': tuple, 'safe_stop': bool, 'main_socket': socket.socket}
    __slots__ = ['address', 'safe_stop', 'main_socket']

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
            use.start_thread(connectNew, _args=(initiate_conn,Nomad.currently_in_connection))
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
