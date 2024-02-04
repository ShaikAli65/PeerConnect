import subprocess
import tkinter as tk
import platform
from tkinter import filedialog
from core import *
from logs import *
import core.nomad as nomad


def file_sender(_to_user_soc: remote_peer.RemotePeer, _data: str,is_dir=False):
    if is_dir:
        directory_sender(_to_user_soc,_data)
    else:
        file = PeerFile(path=_data, obj=_to_user_soc)
        if file.send_meta_data():
            return file.send_file()
        return False


def directory_sender(_to_user_soc: remote_peer.RemotePeer, _data: str):
    pass


def directory_reciever(_conn: socket.socket):
    pass


def file_reciever(_conn: socket.socket):
    nomad.Nomad.currently_in_connection[_conn] = True
    if not _conn:
        with const.PRINT_LOCK:
            print("::Closing connection from recv_file() from core/nomad at line 100")
        return
    getdata_file = PeerFile(recv_soc=_conn)
    if getdata_file.recv_meta_data():
        getdata_file.recv_file()
    return


def open_file_dialog():
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


def open_directory_dialog():
    root = tk.Tk()
    root.withdraw()
    directory_path = filedialog.askdirectory(title="Select a directory")
    if directory_path:
        print("Selected Directory:", directory_path)

    return directory_path if directory_path else None
