import subprocess
import platform

from src.core import *


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
