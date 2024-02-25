from core import *
from core import connectserver as connect_server
from core import requestshandler as manage_requests
from webpage import handle
# from managers import threadmanager
from managers import filemanager
import subprocess
import tkinter as tk
import platform
from tkinter import filedialog


def start_thread(_target, args=()):
    if len(args) != 0:
        thread_recv = threading.Thread(target=_target, args=args)
    else:
        thread_recv = threading.Thread(target=_target, daemon=True)
    thread_recv.start()
    return thread_recv


def is_socket_connected(sock):
    error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    return error == 0


def echo_print(delay_status=False, *args) -> None:
    """Prints the given arguments to the console.

    Args:
        *args: The arguments to print.
        :param delay_status:
    """
    with const.PRINT_LOCK:
        time.sleep(const.anim_delay) if delay_status else None
        print(*args)


def end_session() -> bool:
    """Asynchronously performs cleanup tasks for ending the application session.

    Returns:
        bool: True if cleanup was successful, False otherwise.
    """

    activity_log("::Initiating End Sequence")
    if const.OBJ:
        const.OBJ.end()
    connect_server.end_connection_with_server()
    manage_requests.end_connection()
    handle.end()
    const.LIST_OF_PEERS.clear()
    # threadmanager.end_all_threads()
    # filemanager.end_file_threads()
    return True


def endSequenceWrapper() -> None:
    """Handles ending the application session gracefully upon receiving SIGTERM or SIGINT signals.
    """

    end_session()


class NotInUse(DeprecationWarning):
    """A class to denote deprecated/not currently used functions/methods/classes"""

    def __init__(self, *args, **kwargs):
        pass


def reload_protocol():
    # end_session()

    return None


def open_file_dialog_window():
    if platform.system() == "Windows":
        powershell_script = """
        Add-Type -AssemblyName System.Windows.Forms
        $fileBrowser = New-Object System.Windows.Forms.OpenFileDialog
        [void]$fileBrowser.ShowDialog()
        echo $fileBrowser.FileName
        """
        result = subprocess.run(["powershell.exe", "-Command", powershell_script], stdout=subprocess.PIPE, text=True)
        return result.stdout.strip()
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="Select a file")
    return file_path if file_path else None


def open_directory_dialog_window():
    root = tk.Tk()
    root.withdraw()
    directory_path = filedialog.askdirectory(title="Select a directory")
    if directory_path:
        print("Selected Directory:", directory_path)

    return directory_path if directory_path else None


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
