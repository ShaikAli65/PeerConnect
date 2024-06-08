from importlib import import_module
from collections import defaultdict
from types import ModuleType

import src.avails.connect
from ..core import *
from ..avails import useables as use
from ..avails.remotepeer import RemotePeer

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
        'RecentConnections': ModuleType,
    }
    __slots__ = 'address', 'controller', 'selector', 'main_socket', 'currently_in_connection', 'RecentConnections', 'socket_handler'

    def __init__(self, ip='localhost', port=8088):
        self.address = (ip, port)
        self.controller = ThreadActuator(None)
        use.echo_print("::Initiating Nomad Object", self.address)
        self.main_socket = connect.create_server(self.address, family=const.IP_VERSION, backlog=5)
        self.currently_in_connection = defaultdict(int)
        self.RecentConnections = getattr(import_module('src.core.senders'), 'RecentConnections')
        self.socket_handler = SocketLoop()

    def __resetSocket(self):
        self.main_socket = connect.create_server(self.address, family=const.IP_VERSION,backlog=5)

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
            use.echo_print("verified peer", _id)  # debug
            return _id

    def __accept_connection(self):
        initial_conn = None
        try:
            initial_conn, _ = self.main_socket.accept()
            use.echo_print(f"New connection from {_}")
            peer_id = self.verify(initial_conn)
            if peer_id:
                self.socket_handler.register_sock(initial_conn, peer_id)
                self.RecentConnections.addSocket(peer_id, initial_conn)
            else:
                initial_conn.close()
        except (socket.error, OSError) as e:
            error_log(f"Socket error: at {func_str(Nomad.__accept_connection)} exp:{e}")
            initial_conn.close()

    def initiate(self):
        self.main_socket.listen(3)
        const.PAGE_HANDLE_CALL.wait()
        use.echo_print("::Listening for connections", self.main_socket)
        threading.Thread(target=self.socket_handler.start_loop).start()
        with self.main_socket:
            reads_list = [self.main_socket, self.controller.reader]
            while True:
                reads, _, _ = select.select(reads_list, [], [])
                if self.controller.to_stop is True:
                    use.echo_print("::Nomad Object Ended")
                    return
                if len(self.currently_in_connection) > 10:
                    time.sleep(10)  # limiting rate just in case of more no. of different connections
                self.__accept_connection()

    def end(self):
        self.socket_handler.stop_loop()
        self.controller.signal_stopping()
        self.currently_in_connection.fromkeys(self.currently_in_connection, 0)
        # self.main_socket.close() if self.main_socket else None

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'

    def __del__(self):
        # self.main_socket.close()
        self.controller.signal_stopping()
        self.socket_handler.stop_loop()


class SocketLoop(selectors.DefaultSelector):
    # TODO: ADD SOCKET EXPIRY TIMER THREAD
    def __init__(self):
        super().__init__()
        # a custom object to be used to wake select call when needed, instead of polling
        self._controller = ThreadActuator(threading.current_thread())
        thread_handler.register(self._controller, NOMADS)
        self.threads = []
        self.register(self._controller, selectors.EVENT_READ)
        self.currently_in_connection = defaultdict(int)
        self.RecentConnections = getattr(import_module('src.core.senders'), 'RecentConnections')

    def register_sock(self, file_desc, peer_id):
        self.register(file_desc, selectors.EVENT_READ, peer_id)
        self._controller.write()
        self._controller.clear_reader()
        use.echo_print(" ".join(str(x) for x in self.get_map()))

    def start_loop(self):
        controller = self._controller
        controller_fileno = controller.fileno()
        # _selector =
        while True:
            events = self.select()
            if controller.to_stop:
                use.echo_print("::Nomad connections ended")
                return
            try:
                for event, _ in events:
                    file_desc = event.fileobj
                    if controller_fileno != file_desc.fileno():
                        self.connect_new(file_desc, event.data)
            except (ConnectionResetError,ConnectionAbortedError):
                pass

    def start_thread(self, function, *args):
        thread = threading.Thread(target=function, args=args)
        thread.daemon = True
        thread.start()
        self.threads.append(thread)

    def connect_new(self,_conn, peer_id):
        try:
            if _conn.recv(1, socket.MSG_PEEK) == b'':
                self.unregister(_conn)
                use.echo_print(f"::Connection closed by peer at {func_str(SocketLoop.connect_new)}", _conn)
                return
            _data = DataWeaver().receive(_conn)
            # use.echo_print('data from peer :\n', _data)  # debug
        except (ConnectionResetError, socket.error) as e:
            self.unregister(_conn)
            use.echo_print(f"::Connection error: at {func_str(SocketLoop.connect_new)} exp:{e}", _conn)
            return
        except TimeoutError:
            return

        if _data.header == const.CMD_TEXT:
            asyncio.run(handle_data.feed_user_data_to_page(_data.content, _data.id))
        elif _data.header == const.CMD_RECV_FILE:
            self.start_thread(filemanager.file_receiver, _data)
        elif _data.header == const.CMD_RECV_FILE_AGAIN:
            self.start_thread(filemanager.re_receive_file, _data)
        elif _data.header == const.CMD_RECV_DIR:
            self.start_thread(directorymanager.directoryReceiver,_data)
        elif _data.header == const.CMD_CLOSING_HEADER:
            self.unregister(_conn)
            self.disconnect_user(_conn, self._controller, peer_id)
            return

    def disconnect_user(self, _conn, _controller, _id):
        self.currently_in_connection[_id] -= 1
        with _conn:
            if src.avails.connect.is_socket_connected(_conn):
                DataWeaver(header=const.CMD_CLOSING_HEADER).send(_conn)
        use.echo_print(f"::Closing connection at {func_str(SocketLoop.disconnect_user)}\n", peer_list.get_peer(_id))
        self.RecentConnections.force_remove(peer_id=_id)
        thread_handler.delete(_controller, NOMADS)

    def stop_loop(self):
        self._controller.signal_stopping()
