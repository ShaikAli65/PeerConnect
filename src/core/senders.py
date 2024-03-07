import threading
from collections import deque
import socket

from src.logs import error_log

from src.avails.textobject import DataWeaver
from src.avails import constants as const, useables as use
from src.avails.remotepeer import RemotePeer
from src.avails.useables import is_socket_connected, echo_print, get_peer_obj_from_sock
from src.managers import filemanager


class RecentConnections:
    """
    Decorator class to manage a cache of recent connected sockets based on the IP address.

    Attributes:
    - cache_size (int): The maximum number of sockets to cache.
    - connection_sockets (deque[socket.socket]): A deque to store the connected sockets.
    - peers (deque): A deque to store the IDs of the remote peers.

    Args:
    - function (callable): The function to be decorated.

    Returns:
    - callable: The decorated function.
    """
    thread_safe = threading.Lock()
    cache_size = 4
    connection_sockets: deque[socket.socket] = deque(maxlen=cache_size)
    peers = deque(maxlen=cache_size)

    def __init__(self, function):
        self.function = function

    def __call__(self, argument, sock=None):
        """
        Call method to manage the cache and call the decorated function.
        Determines the connected socket based on the dataweaver object(id)
        retrieves it from cache and passes to function
        Args:
        - argument (DataWeaver): The data wrapper object containing the ID.
        - sock (socket.socket): The connected socket to use, if available.

        Returns:
        - Any: The result of the decorated function.
        """
        get_socket = self.giveSocket(argument)
        return self.function(argument, get_socket)

    @classmethod
    def giveSocket(cls, datawrap):
        """
        Get a socket from the cache based on the ID in the data wrapper.

        Args:
        - datawrap (DataWeaver): The data wrapper object containing the ID.

        Returns:
        - socket or None: The cached socket, or None if not found.
        """
        try:
            with cls.thread_safe:
                for connected_socket in cls.connection_sockets:
                    if connected_socket.getpeername()[0] == datawrap.id:
                        return cls.addConnection(get_peer_obj_from_sock(connected_socket))
        except socket.error:
            pass
        # --debug if the current socket expires

    @classmethod
    def check_connection(cls,peer_obj:RemotePeer):
        for _socket in cls.connection_sockets:
            try:
                if _socket.getpeername()[0] == peer_obj.id:
                    if not is_socket_connected(_socket):
                        print("found but not connected",_socket)
                        cls.removeConnection(peer_obj,_socket)
                        return False
                    else:
                        print("found but connected",_socket)
                        return _socket
            except OSError:
                cls.removeConnection(peer_obj, _socket)
                return False

    @classmethod
    def addConnection(cls, peer_obj: RemotePeer):
        """
        Add a new connection to the cache.
        This needs to called before using any decorated function at every cost
        Args:
        - peer_obj (RemotePeer): The remote peer object to connect to.

        Returns:
        - bool: True if the connection was successful, False otherwise.
        """
        try:
            if peer_obj.id in cls.peers:
                # echo_print(False, "cache hit ! !",peer_obj.username,cls.peers)
                if conn := cls.check_connection(peer_obj):
                    return conn
        except AttributeError:
            cls.peers.clear()
            cls.connection_sockets.clear()
        conn = socket.socket(const.IP_VERSION, const.PROTOCOL)
        conn.settimeout(4)
        try:
            # print("Creating connection", peer_obj.uri)
            conn.connect(peer_obj.uri)
            echo_print(False, "Connected :",peer_obj.username)
            cls.peers.append(peer_obj.id)
            cls.connection_sockets.append(conn)
        except socket.error:
            echo_print(False, "Can't connect :",peer_obj.username)
            pass  # handle error
        return conn

    @classmethod
    def removeConnection(cls,peer_obj:RemotePeer, _socket:socket.socket):
        cls.peers.remove(peer_obj.id)
        cls.connection_sockets.remove(_socket)

    @classmethod
    def end(cls):
        for _socket in cls.connection_sockets:
            try:
                _socket.settimeout(1)
                DataWeaver(header=const.CMD_CLOSING_HEADER).send(_socket)
                _socket.close()
            except socket.error:
                pass
            finally:
                _socket.close() if _socket else None
        cls.connection_sockets.clear()
        cls.peers.clear()


@RecentConnections
async def send_message(data:DataWeaver, sock=None):
    """
    A Wrapper function to function at {nomad.send()}
    Provides Error Handling And Ensures robustness of sending data.
    What is going on here??, can't be understood
    the thing with the decorator is different here, look into decorator's doc string for further reference
    :param data:
    :param sock:
    :return bool:
    """
    try:
        data['id'] = const.THIS_OBJECT.id
        data.send(sock)
    except socket.error as exp:
        print(f"got error at handle/send_message :{exp}")
        error_log(f"got error at handle/send_message :{exp}")
    except AttributeError as exp:
        print(f"got error at handle/send_message :{exp}")
        error_log(f"got error at handle/send_message :{exp}")  # need to be handled more


@RecentConnections
async def send_file(_path,sock=None):
    """
    A Wrapper function to function at {filemanager.file_sender()}
    Provides Error Handling And Ensures robustness of sending data.
    What is going on here??, can't be understood
    the thing with the decorator is different here, look into decorator's doc string for further reference
    :param _path:
    :param sock:
    :return bool:
    """
    try:
        use.start_thread(_target=filemanager.file_sender,_args=(_path['content'], sock))
    except socket.error:
        pass
    pass


async def send_file_with_window(_path, user_id):
    with const.LOCK_LIST_PEERS:
        peer_remote_obj = const.LIST_OF_PEERS[user_id]
    use.echo_print(False, "at send_file_with_window : ", peer_remote_obj, _path)
    use.start_thread(_target=filemanager.pop_file_selector_and_send, _args=(peer_remote_obj,))
    return


async def send_dir_with_window(_path, user_id):
    peer_remote_obj = use.get_peer_obj_from_id(user_id)
    use.echo_print(False, "at send_dir_with_window : ", peer_remote_obj, _path)
    use.start_thread(_target=filemanager.pop_dir_selector_and_send, _args=(peer_remote_obj,))
    return
