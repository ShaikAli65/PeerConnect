from importlib import import_module
from collections import defaultdict
from typing import Any

from ..core import *
from ..avails import useables as use
from ..avails.remotepeer import RemotePeer

from ..avails.constants import NOMAD_FLAG  # control flag
from ..managers import directorymanager, filemanager
from ..managers.thread_manager import thread_handler, NOMADS
from ..webpage_handlers import handle_data
from ..avails.textobject import DataWeaver, SimplePeerText


class Nomad(object):
    __annotations__ = {
        'address': tuple,
        '__control_flag': threading.Event,
        'main_socket': socket.socket,
        'controller':ThreadActuator,
        'currently_in_connection':defaultdict,
        'RecentConnections':Any,
    }
    __slots__ = 'address', 'controller', 'selector', 'main_socket', 'currently_in_connection', 'RecentConnections'

    def __init__(self, ip='localhost', port=8088):
        self.address = (ip, port)
        self.controller = ThreadActuator(None)
        const.THIS_OBJECT = RemotePeer(const.USERNAME, ip, port, report=const.PORT_REQ, status=1)
        use.echo_print("::Initiating Nomad Object", self.address)
        self.main_socket = connect.Socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)
        self.currently_in_connection = defaultdict(int)
        self.RecentConnections = getattr(import_module('src.core.senders'), 'RecentConnections')

    def __resetSocket(self):
        self.main_socket = connect.Socket(const.IP_VERSION, const.PROTOCOL)
        self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.main_socket.bind(self.address)
        self.main_socket.listen()

    def verify(self, _conn):
        """
        :param _conn: connection from peer
        :returns peer_id: if verification is successful else None (implying socket to be removed)
        """
        # hand_shake = DataWeaver().receive(_conn,controller=self.controller)
        hand_shake = SimplePeerText(refer_sock=_conn).receive(cmp_string=const.CMD_VERIFY_HEADER)
        if hand_shake:
            _id = SimplePeerText(_conn).receive().decode(const.FORMAT)
            if _id not in peer_list:
                return None
            if self.currently_in_connection[_id] > 5:
                return None
            self.currently_in_connection[_id] += 1
            return _id

    def add_receive_thread(self, initial_conn, peer_id):
        th_controller = ThreadActuator(None, NOMAD_FLAG)
        thread = use.start_thread(self.connectNew, _args=(initial_conn,peer_id))  # name these threads .??
        th_controller.thread = thread
        thread_handler.register(th_controller, NOMADS)
        self.RecentConnections.addSocket(peer_id, initial_conn)

    def __acceptConnections(self):
        initial_conn = None
        try:
            initial_conn, _ = self.main_socket.accept()
            use.echo_print(f"New connection from {_}")
            peer_id = self.verify(initial_conn)
            if peer_id:
                self.add_receive_thread(initial_conn, peer_id)
            else:
                initial_conn.close()
        except (socket.error, OSError) as e:
            error_log(f"Socket error: at {func_str(Nomad.__acceptConnections)} exp:{e}")
            initial_conn.close()

    def initiate(self):
        self.main_socket.listen(3)
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print("::Listening for connections", self.main_socket)
        while True:
            reads, _, _ = select.select([self.main_socket, self.controller.reader], [], [])
            if self.controller.to_stop is True:
                use.echo_print("::Nomad Object Ended")
                return
            if self.main_socket not in reads:
                continue
            if len(self.currently_in_connection) > 10:
                time.sleep(10)  # limiting rate just in case of more no. of different connections
            self.__acceptConnections()

    def connectNew(self, _conn, peer_id):
        with _conn:
            while True:
                readable, _, _ = select.select([_conn, self.controller.reader], [], [], 500)
                if self.controller.to_stop is True:
                    return
                if _conn not in readable:
                    use.echo_print(f"::Connection timed out : at {func_str(self.connectNew)}", _conn.getpeername())
                    self.disconnectUser(_conn, self.controller, peer_id)
                    return
                if _conn.recv(1, socket.MSG_PEEK) == b'':
                    use.echo_print(f"::Connection closed by peer at {func_str(self.connectNew)}", _conn.getpeername())
                    return
                _data = DataWeaver().receive(_conn)
                use.echo_print('data from peer :\n', _data)
                if _data.header == const.CMD_CLOSING_HEADER:
                    self.disconnectUser(_conn, self.controller, peer_id)
                    return
                self.flow_data(_data)

    @staticmethod
    def flow_data(_data):
        if _data.header == const.CMD_TEXT:
            asyncio.run(handle_data.feed_user_data_to_page(_data.content, _data.id))
        elif _data.header == const.CMD_RECV_FILE:
            use.start_thread(_target=filemanager.file_receiver, _args=(_data,))
        elif _data.header == const.CMD_RECV_FILE_AGAIN:
            use.start_thread(_target=filemanager.re_receive_file, _args=(_data,))
        elif _data.header == const.CMD_RECV_DIR:
            directorymanager.directoryReceiver(refer=_data)

    def disconnectUser(self, _conn, _controller, _id):
        self.currently_in_connection[_id] -= 1
        with _conn:
            DataWeaver(header=const.CMD_CLOSING_HEADER).send(_conn)
            use.echo_print(f"::Closing connection at {func_str(Nomad.disconnectUser)}", _conn.getpeername())
        self.RecentConnections.force_remove(peer_id=_id)
        _controller.signal_stopping()
        thread_handler.delete(_controller, NOMADS)

    def end(self):
        self.controller.signal_stopping()
        self.currently_in_connection.fromkeys(self.currently_in_connection, 0)
        self.main_socket.close() if self.main_socket else None

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'

    def __del__(self):
        self.main_socket.close()
        self.controller.signal_stopping()
        # for sock in self.currently_in_connection.keys():
        # sock.close()
