import os
import pickle
from multiprocessing import Process
from os import PathLike
from pathlib import Path
from typing import Union
from zipfile import ZipFile, ZIP_DEFLATED

import tqdm
from src.logs import error_log

from src.avails.fileobject import PeerFile
from src.avails.remotepeer import RemotePeer
from src.core import *
from src.avails import useables as use
from src.avails import remotepeer as remote_peer
from src.avails.textobject import SimplePeerText, DataWeaver
from src.managers.filemanager import fileSender


def make_directory_structure(path: Path):
    d_dir = Path(const.PATH_DOWNLOAD)

    def _fill_in(p: Path):
        nonlocal d_dir
        for f in p.iterdir():
            if f.is_file():
                d = d_dir / f.relative_to(path)
                d.touch(exist_ok=True)
            elif f.is_dir():
                d = d_dir / f.relative_to(path)
                d.mkdir(parents=True, exist_ok=True)
                _fill_in(f)
        return

    parent = d_dir / path.name
    balancer = 0
    while parent.exists():
        parent = d_dir / f"{path.name}({balancer})"
        balancer += 1
    parent.mkdir(parents=True, exist_ok=True)
    _fill_in(path)
    use.echo_print(True, f"::Created directory structure at {parent}")


def send_files(dir_socket, dir_path):
    for x in dir_path.glob('**/*'):
        if x.is_file():
            pass
    pass


def directory_sender(receiver_obj: remote_peer.RemotePeer, dir_path: str):
    dir_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
    dir_socket.connect(receiver_obj.uri)
    SimplePeerText(dir_socket, const.CMD_RECV_DIR_LITE, byte_able=False).send()
    dir_path = Path(dir_path)
    print(f"sending directory{dir_path} to ", receiver_obj)
    serialized_path = pickle.dumps(dir_path)
    dir_socket.sendall(struct.pack('!Q', len(serialized_path)))
    dir_socket.sendall(serialized_path)
    time.sleep(0.02)
    send_files(dir_socket, dir_path)
    pass


def directory_receiver(_conn):
    with const.LOCK_LIST_PEERS:
        sender_obj = const.LIST_OF_PEERS[_conn.getpeername()[0]]
    sender_obj.increment_file_count()
    dir_len = struct.unpack('!Q', _conn.recv(8))[0]
    dir_path = pickle.loads(_conn.recv(dir_len))
    dir_path: Path = Path(dir_path)
    make_directory_structure(dir_path)
    return dir_path.name


def directorySender(_data: str, recv_sock:socket.socket):
    receiver_obj: RemotePeer = use.get_peer_obj_from_sock(recv_sock)
    provisional_name = f"temp{receiver_obj.get_file_count()}!!{receiver_obj.id}.zip"
    receiver_obj.increment_file_count()

    zipper_process = Process(target=zipDir, args=(provisional_name, _data))
    zipper_process.start()
    zipper_process.join()

    fileSender(provisional_name, recv_sock, is_dir=True)
    use.echo_print(False, "sent zip file: ", provisional_name)
    os.remove(provisional_name)
    pass


def directoryReceiver(refer: DataWeaver):
    tup = refer.id.split('(^)')
    file = PeerFile(uri=(tup[0], int(tup[1])))
    metadata = json.loads(refer.content)
    file.set_meta_data(filename=metadata['name'], file_size=int(metadata['size']))
    if file.recv_meta_data():
        file.recv_file()

    file_unzip_path = os.path.join(const.PATH_DOWNLOAD, file.filename)

    unzip_process = Process(target=unZipper, args=(file_unzip_path, const.PATH_DOWNLOAD))
    unzip_process.start()
    unzip_process.join()

    return file.filename


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
    os.remove(zip_path)
    return
