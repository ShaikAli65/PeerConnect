import pickle
import socket
import time
from pathlib import Path

from src.core import *
from zipfile import ZIP_DEFLATED, ZipFile
from src.avails import useables as use
from src.avails import remotepeer as remote_peer
from src.avails.textobject import SimplePeerText


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


def directory_reciever(_conn):
    with const.LOCK_LIST_PEERS:
        sender_obj = const.LIST_OF_PEERS[_conn.getpeername()[0]]
    sender_obj.increment_file_count()
    dir_len = struct.unpack('!Q', _conn.recv(8))[0]
    dir_path = pickle.loads(_conn.recv(dir_len))
    dir_path: Path = Path(dir_path)
    make_directory_structure(dir_path)
    return dir_path.name
