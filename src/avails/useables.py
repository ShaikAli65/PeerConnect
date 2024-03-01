from src.core import *
import subprocess
import platform
from PyQt5.QtWidgets import QApplication, QFileDialog

# def open_file():
#   """Opens the system-like file picker dialog."""
#   filepath, _ = QFileDialog.getOpenFileName()
#   if filepath:
#     # Do something with the selected file
#     print(f"You selected: {filepath}")

# if __name__ == "__main__":
#   app = QApplication([])
#   open_file()
#   app.exec_()


def start_thread(_target, _args=()):
    if len(_args) != 0:
        thread_recv = threading.Thread(target=_target, args=_args)
    else:
        thread_recv = threading.Thread(target=_target, daemon=True)
    thread_recv.start()
    return thread_recv


def is_socket_connected(sock):
    error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    return error == 0


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
    app = QApplication([])
    file_path, _ = QFileDialog.getOpenFileName()
    return file_path if file_path else None


def open_directory_dialog_window():
    app = QApplication([])
    dir_path = QFileDialog.getExistingDirectory()
    app.exec_()
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
