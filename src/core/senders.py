
from typing import Optional
from src.core import *
from src.avails.textobject import DataWeaver
from src.avails import constants as const, useables as use
from src.avails.remotepeer import RemotePeer
from src.avails.useables import echo_print
from src.managers import filemanager
from src.managers import directorymanager

from collections import OrderedDict


class SocketCache:
    def __init__(self, max_limit=4):
        self.socket_cache: dict[str: connect.Socket] = OrderedDict()
        self.max_limit = max_limit
        self.__thread_lock = threading.Lock()

    def appendPeer(self, peer_id: str, peer_socket):
        with self.__thread_lock:
            if len(self.socket_cache) >= self.max_limit:
                self.socket_cache.popitem(last=False)
            self.socket_cache[peer_id] = peer_socket
        return peer_socket

    def get_socket(self, peer_id) -> Union[connect.Socket, None]:
        with self.__thread_lock:
            return self.socket_cache.get(peer_id, None)

    def remove(self, peer_id):
        with self.__thread_lock:
            if peer_id in self.socket_cache:
                del self.socket_cache[peer_id]

    def clear(self):
        with self.__thread_lock:
            self.socket_cache.clear()

    def __contains__(self, item: str):
        return item in self.socket_cache


class RecentConnections:
    connected_sockets = SocketCache()
    current_connected: Optional[connect.Socket] = None

    def __init__(self, function):
        self.__code__ = function.__code__
        self.__name__ = function.__name__
        self.function = function

    def __call__(self, argument):
        return self.function(argument, RecentConnections.current_connected)

    @classmethod
    def addConnection(cls, peer_obj: RemotePeer):
        connection_socket = use.create_socket_to_peer(_peer_obj=peer_obj, to_which=const.BASIC_URI_CONNECTOR)
        cls.connected_sockets.appendPeer(peer_obj.id, peer_socket=connection_socket)
        return connection_socket

    @classmethod
    def addSocket(cls, peer_id: str, peer_socket):
        cls.connected_sockets.appendPeer(peer_id, peer_socket)

    @classmethod
    def connect_peer(cls, peer_obj: RemotePeer):
        if peer_obj.id not in cls.connected_sockets:
            try:
                cls.current_connected = cls.addConnection(peer_obj)
                print("cache miss --current : ", peer_obj.username, cls.current_connected.getpeername()[:2],cls.current_connected.getsockname()[:2])
            except socket.error:
                use.echo_print("handle signal to page, that we can't reach user, or he is offline")
                pass
            return

        supposed_to_be_connected_socket = cls.connected_sockets.get_socket(peer_id=peer_obj.id)
        if use.is_socket_connected(supposed_to_be_connected_socket):
            cls.current_connected = supposed_to_be_connected_socket
            pr_str = f"cache hit !{f"{peer_obj.username[:10]}..." if len(peer_obj.username) > 10 else peer_obj.username}! and socket is connected"
            use.echo_print(pr_str, supposed_to_be_connected_socket.getpeername())
        else:
            cls.connected_sockets.remove(peer_id=peer_obj.id)
            use.echo_print("cache hit !! socket not connected trying to reconnect")
            cls.connect_peer(peer_obj)

    @classmethod
    def force_remove(cls, peer_id: str):
        cls.connected_sockets.remove(peer_id=peer_id)

    @classmethod
    def end(cls):
        use.echo_print("::Cleared senders")
        cls.connected_sockets.clear()


@RecentConnections
def sendMessage(data: DataWeaver, sock:socket = None):
    """
    A Wrapper function to function at {nomad.send()}
    Provides Error Handling And Ensures robustness of sending data.
    What is going on here ?
    the thing with the decorator is different here, look into decorator's doc string for further reference
    :param data:
    :param sock:
    :return bool:p
    """
    back_up_id = data.id  # back up the id, to be used in case of error
    try:
        data['id'] = const.THIS_OBJECT.id  # Changing the id to this peer's id
        data.send(sock)
        echo_print("sent message to ", sock.getpeername())
    except socket.error as exp:
        print(f"got error at {sendMessage.__name__}()/{os.path.relpath(sendMessage.__code__.co_filename)} :{exp}",sock.getpeername())
        error_log(f"got error at handle/send_message :{exp}")
        RecentConnections.force_remove(back_up_id)
    # except AttributeError as exp:
    #     print(f"got error at handle/send_message :{exp}")
    #     error_log(f"got error at handle/send_message :{exp}")  # need to be handled more


@RecentConnections
def sendFile(_path: DataWeaver, sock=None):
    """
    A Wrapper function to function at {filemanager.fileSender()}
    Provides Error Handling And Ensures robustness of sending data.
    What is going on here??
    the thing with the decorator is different, look into decorator's doc string for further reference
    :param _path:
    :param sock:
    :return bool:
    """
    back_up_id = _path.id
    try:
        use.start_thread(_target=filemanager.fileSender, _args=(_path, sock))
    except socket.error:
        RecentConnections.force_remove(back_up_id)


@RecentConnections
def sendDir(_path, sock=None):
    use.start_thread(_target=directorymanager.directorySender, _args=(_path, sock))
