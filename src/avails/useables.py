import socket
import subprocess
import platform
import random
from PyQt5.QtWidgets import QApplication, QFileDialog

import src.avails.remotepeer
from src.core import *
from src.configurations.bootup import is_port_empty


def start_thread(_target, _args=()):
    if len(_args) != 0:
        thread_recv = threading.Thread(target=_target, args=_args)
    else:
        thread_recv = threading.Thread(target=_target, daemon=True)
    thread_recv.start()
    return thread_recv


def is_socket_connected(sock: socket.socket):
    try:
        sock.getpeername()
        sock.setblocking(False)
        data = sock.recv(1, socket.MSG_PEEK)
        return False if data == b'' else True
    except BlockingIOError:
        return True
    except (ConnectionResetError, ConnectionError, ConnectionAbortedError, OSError):
        return False
    finally:
        sock.setblocking(True)


def echo_print(delay_status, *args) -> None:
    """Prints the given arguments to the console.

    Args:
        *args: The arguments to print.
        :param delay_status:
    """
    with const.LOCK_PRINT:
        time.sleep(const.anim_delay) if delay_status else None
        print(*args)


class NotInUse(DeprecationWarning):
    """A class to denote deprecated/not currently used functions/methods/classes"""

    def __init__(self, *args, **kwargs):
        pass


def reload_protocol():
    # end_session()

    return None


def open_file_dialog_window():
    """Opens the system-like file picker dialog."""
    QApplication([])
    file_path, _ = QFileDialog.getOpenFileName()
    return file_path if file_path else None


def open_directory_dialog_window():
    QApplication([])
    dir_path = QFileDialog.getExistingDirectory()
    return dir_path if dir_path else None


def open_file(content):
    if platform.system() == "Windows":
        powershell_script = f"""
        $file = "{content}"
        Invoke-Item $file
        """
        result = subprocess.run(["powershell.exe", "-Command", powershell_script], stdout=subprocess.PIPE, text=True)
        return result.stdout.strip()
    elif platform.system() == "Darwin":
        subprocess.run(["open", content])
    else:
        subprocess.run(["xdg-open", content])
    return None


def get_free_port() -> int:
    """Gets a free port from the system."""
    random_port = random.randint(1024, 65535)
    while not is_port_empty(random_port):
        random_port = random.randint(1024, 65535)
    return random_port


def get_peer_obj_from_sock(_conn: socket.socket):
    """Retrieves peer object from list using connected socket using ip address"""
    with const.LOCK_LIST_PEERS:
        return const.LIST_OF_PEERS.get(_conn.getpeername()[0], None)


def get_peer_obj_from_id(user_id: str) -> src.avails.remotepeer.RemotePeer:
    """
    Retrieves peer object from list given id
    :param user_id:
    """
    with const.LOCK_LIST_PEERS:
        return const.LIST_OF_PEERS[user_id]


def get_profile_from_username(username: str):
    """
    Retrieves profile object from list given username
    :param username:
    """
    for profile in const.PROFILE_LIST:
        if profile.username == username:
            return profile
    return None


def create_socket_to_peer(_peer_obj=None, peer_id="", to_which: int = const.BASIC_URI_CONNECTOR,timeout=0) -> socket.socket:
    """
    Creates a basic socket connection to peer id passed in,
    or to the peer_obj passed in.
    The another argument :param to_which: specifies to what uri should the connection made,
    pass :param const.REQ_URI_CONNECT: to connect to req_uri of peer
    :param timeout:
    :param _peer_obj:
    :param peer_id:
    :param to_which:
    :return:
    """
    peer_obj = _peer_obj if _peer_obj is not None else get_peer_obj_from_id(peer_id)
    addr = peer_obj.req_uri if to_which == const.REQ_URI_CONNECT else peer_obj.uri

    soc = socket.socket(const.IP_VERSION, const.PROTOCOL)
    if not timeout == 0:
        soc.settimeout(timeout)
    soc.connect(addr)

    return soc
