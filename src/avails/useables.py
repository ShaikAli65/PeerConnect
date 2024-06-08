import subprocess
import platform
import random

from src.core import *
from src.configurations.boot_up import is_port_empty


def start_thread(_target, _args=()):
    if len(_args) != 0:
        thread_recv = threading.Thread(target=_target, args=_args)
    else:
        thread_recv = threading.Thread(target=_target, daemon=True)
    # thread_recv.name = "peer-connect"
    thread_recv.start()
    return thread_recv


def echo_print(*args) -> None:
    """Prints the given arguments to the console.

    Args:
        *args: The arguments to print.
    """
    with const.LOCK_PRINT:
        print(*args)

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


