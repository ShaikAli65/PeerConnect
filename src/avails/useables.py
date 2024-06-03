import subprocess
import platform
import random
from typing import Optional


from src.core import *
from src.configurations.boot_up import is_port_empty

from src.avails.constants import USEABLES_FLAG  # control_flag


def safe_stop():
    return USEABLES_FLAG.is_set()


def start_thread(_target, _args=()):
    if len(_args) != 0:
        thread_recv = threading.Thread(target=_target, args=_args)
    else:
        thread_recv = threading.Thread(target=_target, daemon=True)
    # thread_recv.name = "peer-connect"
    thread_recv.start()
    return thread_recv


def is_socket_connected(sock: connect.Socket):
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
        try:
            sock.setblocking(True)
        except OSError:
            return False


def echo_print(*args) -> None:
    """Prints the given arguments to the console.

    Args:
        *args: The arguments to print.
    """
    with const.LOCK_PRINT:
        print(*args)


class NotInUse(DeprecationWarning):
    """A class to denote deprecated/not currently used functions/methods/classes"""

    def __init__(self, *args, **kwargs):
        pass


def reload_protocol():
    # end_session()

    return None


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


BASIC_URI_CONNECT = 13
REQ_URI_CONNECT = 12


def create_conn_to_peer(_peer_obj=None, peer_id="", to_which: int = BASIC_URI_CONNECT, timeout=0):
    """
    Creates a basic socket connection to peer id passed in, or to the peer_obj passed in.
    peer_obj is given higher priority
    The another argument :param to_which: specifies to what uri should the connection made,
    pass :param const.REQ_URI_CONNECT: to connect to req_uri of peer
    :param timeout:
    :param _peer_obj:
    :param peer_id:
    :param to_which:
    :return:
    """
    peer_obj = _peer_obj or peer_list.get_peer(peer_id)
    addr = peer_obj.req_uri if to_which == REQ_URI_CONNECT else peer_obj.uri

    soc = connect.Socket(const.IP_VERSION, const.PROTOCOL)
    soc.settimeout(timeout or None)
    soc.connect(addr)
    # connect.create_connection(addr)
    return soc


