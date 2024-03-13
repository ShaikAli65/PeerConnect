from collections import deque

from src.core import *
from src.avails.textobject import DataWeaver
from src.avails import constants as const, useables as use
from src.avails.remotepeer import RemotePeer
from src.avails.useables import is_socket_connected, echo_print  # , get_peer_obj_from_sock
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
    connected_peers = deque(maxlen=cache_size)
    current_connected = None

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
        use.start_thread(_target=self.function, _args=(RecentConnections.current_connected,))

    @classmethod
    def connect_peer(cls, peer_obj: RemotePeer):
        if cls.current_connected is None:
            echo_print(False, "found nowhere adding user ", peer_obj.username, "queue:",cls.connection_sockets)
            cls.current_connected = cls.addConnection(peer_obj)
            return

        if cls.current_connected.getpeername()[0] == peer_obj.id:
            if is_socket_connected(cls.current_connected):
                # echo_print(False,"already connected ",peer_obj.username, "queue:",cls.connection_sockets)
                return
            # echo_print(False,"not connected ",peer_obj.username, "queue:",cls.connection_sockets)
            if connection := cls.addConnection(peer_obj) is False or None:
                pass  # handle error further (send data to page)
            cls.current_connected = connection
            return

        echo_print(False,"not current connected ",peer_obj.username, "queue:",cls.connection_sockets)
        for _soc in cls.connection_sockets.copy():
            if _soc.getpeername()[0] == peer_obj.id:
                if is_socket_connected(_soc):
                    echo_print(False,"found connected in cache ",peer_obj.username, "queue:",cls.connection_sockets)

                    cls.current_connected = _soc
                    return
                else:
                    # echo_print(False,"found disconnected in cache ",peer_obj.username, "queue:",cls.connection_sockets)
                    cls.removeConnection(peer_obj, _soc)
                break

        echo_print(False,"found nowhere adding user ",peer_obj.username, "queue:",cls.connection_sockets)
        cls.addConnection(peer_obj)

    @classmethod
    def addConnection(cls, peer_obj: RemotePeer) -> Union[bool,socket.socket]:
        """
        Add a new connection to the cache.
        This needs to called before using any decorated function at every cost
        Args:
        - peer_obj (RemotePeer): The remote peer object to connect to.

        Returns:
        - bool: True if the connection was successful, False otherwise.
        """
        conn = socket.socket(const.IP_VERSION, const.PROTOCOL)
        conn.settimeout(5)
        try:
            print("Creating connection", peer_obj.uri)
            conn.connect(peer_obj.uri)
            # echo_print(False, "Connected :",peer_obj.username, "queue:",cls.connection_sockets)
            cls.connected_peers.append(peer_obj.id)
            cls.connection_sockets.append(conn)
        except socket.error:
            # echo_print(False, "Can't connect :",peer_obj.username, "queue:",cls.connection_sockets)
            pass  # handle error further (send data to page)
            return False
        return conn

    @classmethod
    def removeConnection(cls,peer_obj:RemotePeer, _socket:socket.socket = None):
        cls.connected_peers.remove(peer_obj.id)
        cls.connection_sockets.remove(_socket)
        if cls.current_connected == _socket:    
            cls.current_connected = None
        try:
            _socket.settimeout(1)
            DataWeaver(header=const.CMD_CLOSING_HEADER).send(_socket)
            _socket.close()
        except socket.error:
            pass

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
        cls.connected_peers.clear()

    @classmethod
    def __getSocket(cls, peer_obj):
        pass


@RecentConnections
async def sendMessage(data:DataWeaver, sock=None):
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
        RecentConnections.current_connected = None

    except AttributeError as exp:
        print(f"got error at handle/send_message :{exp}")
        error_log(f"got error at handle/send_message :{exp}")  # need to be handled more


@RecentConnections
async def sendFile(_path, sock=None):
    """
    A Wrapper function to function at {filemanager.fileSender()}
    Provides Error Handling And Ensures robustness of sending data.
    What is going on here??
    the thing with the decorator is different, look into decorator's doc string for further reference
    :param _path:
    :param sock:
    :return bool:
    """
    try:
        use.start_thread(_target=filemanager.fileSender, _args=(_path['content'], sock))
    except socket.error:
        pass
    pass


async def sendFileWithWindow(_path, user_id):
    peer_remote_obj = use.get_peer_obj_from_id(user_id)
    use.echo_print(False, "at sendFileWithWindow : ", peer_remote_obj, _path)
    use.start_thread(_target=filemanager.pop_file_selector_and_send, _args=(peer_remote_obj,))
    return


async def sendDirWithWindow(_path, user_id):
    peer_remote_obj = use.get_peer_obj_from_id(user_id)
    use.echo_print(False, "at sendDirWithWindow : ", peer_remote_obj, _path)
    use.start_thread(_target=filemanager.pop_dir_selector_and_send, _args=(peer_remote_obj,))
    return
