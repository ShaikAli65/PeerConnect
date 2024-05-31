import pickle
from multiprocessing import Process
from zipfile import ZipFile, ZIP_DEFLATED

import tqdm
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog

from src.avails.fileobject import PeerFilePool, make_file_items
from src.core import *
from src.avails import useables as use
from src.avails import remotepeer as remote_peer
from src.avails.textobject import DataWeaver
import tempfile

from pathlib import Path


def do_handshake(_sock, _content):
    bind_addr = (const.THIS_IP, use.get_free_port())
    with connect.create_server(bind_addr, family=const.IP_VERSION, backlog=1) as soc:
        handshake = DataWeaver(header=const.CMD_RECV_DIR, content=_content, _id=bind_addr)
        handshake.send(_sock)
        ggm, _ = soc.accept()
    return ggm


def directorySender(_data: DataWeaver, recv_sock):
    receiver_obj = peer_list.get_peer(_data.id)
    file_name = _data.content
    if not file_name:
        file_name = open_directory_dialog_window()
    temp_path = None
    try:
        temp_path = process_zipping(receiver_obj, file_name)
        files = make_file_items([temp_path, ])
        recv_sock = do_handshake(recv_sock, file_name)
        PeerFilePool(paths=files).send_files(recv_sock)
    finally:
        temp_path.unlink(missing_ok=True)


def directoryReceiver(refer: DataWeaver):
    with connect.Socket(const.IP_VERSION, const.PROTOCOL) as soc:
        soc.connect(tuple(refer.id))
        files = PeerFilePool()
        files.recv_files(soc)
    for file in files:
        process_unzipping(Path(file.path))


def zipDir(zip_name: Union[str, Path], _target):
    src_path = Path(_target).expanduser().resolve(strict=True)
    with ZipFile(zip_name, 'w', ZIP_DEFLATED) as zf:
        progress = tqdm.tqdm(src_path.rglob('*'), desc="Zipping", unit="files")
        for file in src_path.rglob('*'):
            zf.write(file, file.relative_to(src_path.parent))
            progress.update(1)
        progress.close()


def process_zipping(receiver_obj, target):
    with tempfile.NamedTemporaryFile(mode='wb+', prefix=f"peer-conn{receiver_obj.get_file_count()}",
                                     suffix='.zip', delete=False, delete_on_close=False) as temp_file:
        temp_path = Path(temp_file.name)

        zipper_process = Process(target=zipDir, args=(temp_path, target))
        zipper_process.start()
        zipper_process.join()
        zipper_process.close()
    return temp_path


def unZipper(zip_path, destination_path, name_queue):
    with ZipFile(zip_path, 'r') as zip_ref:
        try:
            zip_ref.extractall(destination_path)
        except PermissionError as pe:
            error_log(f"::PermissionError in unzipper()/directory manager.py :{pe}")
    print(f"::Extracted {zip_path} to {destination_path}")
    name_queue.put(zip_ref.namelist())


def process_unzipping(file_path):
    import multiprocessing.queues
    queue = multiprocessing.Queue(1)

    unzip_process = Process(target=unZipper, args=(file_path, const.PATH_DOWNLOAD, queue))
    unzip_process.start()
    unzip_process.join()
    unzip_process.close()
    file_path.unlink(missing_ok=True)
    return queue.get()


def open_directory_dialog_window(_prev_dir=[os.path.join(os.path.expanduser('~'), 'Downloads'), ]):
    _ = QApplication([])
    dialog = QFileDialog()
    dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    dialog.setWindowFlags(Qt.WindowStaysOnTopHint | dialog.windowFlags())
    directory = dialog.getExistingDirectory(directory=_prev_dir[0],
                                            caption="Select directory to send")
    _prev_dir[0] = directory
    return directory


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
    dir_socket = connect.Socket(const.IP_VERSION, const.PROTOCOL)
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
    # use.get_peer_from_id()
    sender_obj = peer_list.get_peer(_conn.getpeername()[0])
    sender_obj.increment_file_count()
    dir_len = struct.unpack('!Q', _conn.recv(8))[0]
    dir_path = pickle.loads(_conn.recv(dir_len))
    dir_path: Path = Path(dir_path)
    make_directory_structure(dir_path, const.PATH_DOWNLOAD)
    return dir_path.name
