import subprocess
import platform
import random
from PyQt5.QtWidgets import QApplication, QFileDialog

from src.core import *
from src.core.configure_app import is_port_empty


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
    except (ConnectionResetError, ConnectionError, ConnectionAbortedError,OSError):
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


def get_peer_obj_from_sock(_conn:socket.socket):
    """Retrieves peer object from list using connected socket using ip address"""
    with const.LOCK_LIST_PEERS:
        return const.LIST_OF_PEERS.get(_conn.getpeername()[0],None)


def get_peer_obj_from_id(user_id:str):
    """
    Retrieves peer object from list given id
    :param user_id:
    """
    with const.LOCK_LIST_PEERS:
        return const.LIST_OF_PEERS[user_id]
