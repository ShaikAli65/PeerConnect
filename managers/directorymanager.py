import pickle
import socket
import time
from pathlib import Path

from core import *
from zipfile import ZIP_DEFLATED, ZipFile
from avails import useables as use
from avails import remotepeer as remote_peer


def make_directory_structure(path: Path):
    def _fill_in(p: Path):
        for f in p.iterdir():
            if f.is_file():
                d = const.PATH_DOWNLOAD / f.relative_to(path)
                d.touch(exist_ok=True)
            elif f.is_dir():
                d = const.PATH_DOWNLOAD / f.relative_to(path)
                d.mkdir(parents=True, exist_ok=True)
                _fill_in(f)
        return
    parent = const.PATH_DOWNLOAD / path.name
    balancer = 0
    while parent.exists():
        parent = const.PATH_DOWNLOAD / f"{path.name}({balancer})"
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
    dir_socket.sendall(const.CMD_RECV_DIR_LITE)
    dir_path = Path(dir_path)
    serialized_path = pickle.dumps(dir_path)
    dir_socket.sendall(struct.pack('!Q', len(serialized_path)))
    dir_socket.sendall(serialized_path)
    time.sleep(0.02)
    send_files(dir_socket, dir_path)
    pass


def directory_reciever(_conn):
    sender_obj = const.LIST_OF_PEERS[_conn.getpeername()[0]]
    sender_obj.increment_file_count()
    dir_len = struct.unpack('!Q', _conn.recv(8))[0]
    dir_path:Path = Path(_conn.recv(dir_len))
    make_directory_structure(dir_path)
    return dir_path.name
