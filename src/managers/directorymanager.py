import pickle
from multiprocessing import Process
from os import PathLike
from zipfile import ZipFile, ZIP_DEFLATED

import tqdm
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog

from src.avails.remotepeer import RemotePeer
from src.core import *
from src.avails import useables as use
from src.avails import remotepeer as remote_peer
from src.avails.textobject import DataWeaver
from src.managers.filemanager import fileSender, fileReceiver

from pathlib import Path


@NotInUse
def make_directory_structure(of_directory: Path, at_directory):

    def _fill_in(current_directory: Path, download_dir):
        for thing in current_directory.iterdir():
            d = download_dir / thing.relative_to(of_directory)
            if thing.is_file():
                d.touch(exist_ok=True)
                pass
            elif thing.is_dir():
                d.mkdir(parents=True, exist_ok=True)
                _fill_in(thing, download_dir)
        return

    parent = at_directory / of_directory.name
    balancer = 0
    while parent.exists():
        parent = at_directory / f"{of_directory.name}({balancer})"
        balancer += 1
    parent.mkdir(parents=True, exist_ok=True)
    _fill_in(of_directory, parent)
    print(f"::Created directory structure at {parent}")
    return Path(parent)


@NotInUse
def send_files(dir_socket, dir_path):
    for x in dir_path.glob('**/*'):
        if x.is_file():
            pass
    pass


@NotInUse
def directory_sender(receiver_obj: remote_peer.RemotePeer, dir_path: str):
    dir_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
    dir_socket.connect(receiver_obj.uri)
    # SimplePeerText(dir_socket, const.CMD_RECV_DIR_LITE, byte_able=False).send()
    dir_path = Path(dir_path)
    DataWeaver(header=const.CMD_RECV_DIR, content=dir_path.name, _id=const.THIS_OBJECT.id)
    print(f"sending directory{dir_path} to ", receiver_obj)
    serialized_path = pickle.dumps(dir_path)
    dir_socket.sendall(struct.pack('!Q', len(serialized_path)))
    dir_socket.sendall(serialized_path)
    time.sleep(0.02)
    send_files(dir_socket, dir_path)
    pass


@NotInUse
def directory_receiver(_conn):
    # use.get_peer_obj_from_id()
    with const.LOCK_LIST_PEERS:
        sender_obj = const.LIST_OF_PEERS[_conn.getpeername()[0]]
    sender_obj.increment_file_count()
    dir_len = struct.unpack('!Q', _conn.recv(8))[0]
    dir_path = pickle.loads(_conn.recv(dir_len))
    dir_path: Path = Path(dir_path)
    make_directory_structure(dir_path,const.PATH_DOWNLOAD)
    return dir_path.name


def directorySender(_data: DataWeaver, recv_sock: socket.socket):
    receiver_obj: RemotePeer = use.get_peer_obj_from_id(_data.id)
    provisional_name = f"temp{receiver_obj.get_file_count()}!!{receiver_obj.id.replace(':','.')}.zip"
    if len(_data.content) == 0:
        _data.content = open_directory_dialog_window()
    provisional_path = Path(os.path.join(const.PATH_DOWNLOAD, provisional_name))
    zipper_process = Process(target=zipDir, args=(provisional_path, _data.content))
    try:
        zipper_process.start()
        zipper_process.join()
        _data.content = provisional_name
        fileSender(_data, recv_sock, is_dir=True)
        use.echo_print("sent zip file: ", provisional_name)
    finally:
        os.remove(provisional_name)


def directoryReceiver(refer: DataWeaver):
    file_name = fileReceiver(refer)
    file_unzip_path = os.path.join(const.PATH_DOWNLOAD, file_name)

    unzip_process = Process(target=unZipper, args=(file_unzip_path, const.PATH_DOWNLOAD))
    unzip_process.start()
    unzip_process.join()
    os.remove(file_unzip_path)
    return file_name


def zipDir(zip_name: str, source_dir: Union[str, PathLike]):
    src_path = Path(source_dir).expanduser().resolve(strict=True)
    with ZipFile(zip_name, 'w', ZIP_DEFLATED) as zf:
        progress = tqdm.tqdm(src_path.rglob('*'), desc="Zipping ", unit=" files")
        for file in src_path.rglob('*'):
            zf.write(file, file.relative_to(src_path.parent))
            progress.update(1)
        progress.close()
    return


def unZipper(zip_path: str, destination_path: str):
    with ZipFile(zip_path, 'r') as zip_ref:
        try:
            zip_ref.extractall(destination_path)
        except PermissionError as pe:
            error_log(f"::PermissionError in unzipper() from core/nomad at line 68: {pe}")
    print(f"::Extracted {zip_path} to {destination_path}")
    return


def open_directory_dialog_window():
    app = QApplication([])
    dialog = QFileDialog()
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
    return dialog.getExistingDirectory(caption="Select directory to send")
