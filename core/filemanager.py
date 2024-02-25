import subprocess
import tkinter as tk
import platform
from tkinter import filedialog
from core import *
from logs import *
import core.nomad as nomad
from avails import dataweaver
from webpage import handle
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from os import PathLike
from typing import Union


def file_sender(_to_user_soc: remote_peer.RemotePeer, _data: str):
    prompt_data = None
    try:
        file = PeerFile(path=_data, obj=_to_user_soc)
        if file.send_meta_data():
            file.send_file()
            prompt_data = dataweaver.DataWeaver(header="thisisaprompt",content=file.filename,_id=_to_user_soc.id)
            return file.filename
        return False
    except NotADirectoryError as nde:
        prompt_data = dataweaver.DataWeaver(header="thisisaprompt", content=nde.filename, _id=_to_user_soc.id)
        directory_sender(_to_user_soc, nde.filename)
    except FileNotFoundError as fne:
        prompt_data = dataweaver.DataWeaver(header="thisisaprompt", content=fne.filename, _id=_to_user_soc.id)
    finally:
        asyncio.run(handle.feed_core_data_to_page(prompt_data))


def directory_sender(_to_user_soc: remote_peer.RemotePeer, _data: str):
    def zip_dir(zip_name: str, source_dir: Union[str, PathLike]):
        src_path = Path(source_dir).expanduser().resolve(strict=True)
        with ZipFile(zip_name, 'w', ZIP_DEFLATED) as zf:
            for file in src_path.rglob('*'):
                zf.write(file, file.relative_to(src_path.parent))
        return zip_name
    zip_dir("temp.zip", _data)
    file_sender(_to_user_soc, "temp.zip")
    pass


def directory_reciever(_conn: socket.socket):
    nomad.Nomad.currently_in_connection[_conn] = True
    if not _conn:
        with const.PRINT_LOCK:
            print("::Closing connection from recv_file() from core/nomad at line 100")
        return
    getdata_file = PeerFile(recv_soc=_conn)
    if getdata_file.recv_meta_data():
        getdata_file.recv_file()
    return getdata_file.filename


def file_reciever(_conn: socket.socket):
    nomad.Nomad.currently_in_connection[_conn] = True
    if not _conn:
        with const.PRINT_LOCK:
            print("::Closing connection from recv_file() from core/nomad at line 100")
        return
    getdata_file = PeerFile(recv_soc=_conn)
    if getdata_file.recv_meta_data():
        getdata_file.recv_file()
    return getdata_file.filename


# def compress_file(file_pa):
#     with open(file_pa, 'rb') as file:
#         compressed_data = zipfile.compress(file.read())
#     return compressed_data


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


