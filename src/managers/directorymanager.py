import asyncio
import os
import socket
import struct
import time
from pathlib import Path

from src.avails import dialogs

DOWNLOADS_DIR = "./down"
CHUNCK_SIZE = 1024


def recv_something(_sock: socket.socket):
    lenght = struct.unpack("!I", _sock.recv(4))[0]
    data = _sock.recv(lenght)
    return data.decode()


def recv_file(_fpath: Path, _size: int, _sock: socket.socket):
    with open(_fpath, "wb") as file:
        while _size > 0:
            data = _sock.recv(min(CHUNCK_SIZE, _size))
            if not data:
                break
            file.write(data)
            _size -= len(data)


def recv_dir(_sock: socket.socket):

    while True:
        raw_length = _sock.recv(4)
        if not raw_length:
            print("I am done")
            return
        con_len = struct.unpack("!I", raw_length)[0]
        rel_path = _sock.recv(con_len).decode()
        abs_path = Path(DOWNLOADS_DIR, rel_path)
        if rel_path.endswith("/"):
            # print("-" * 100)
            os.makedirs(abs_path, exist_ok=True)
            continue
        # print("parent", abs_path.parent)
        os.makedirs(abs_path.parent, exist_ok=True)
        f_size = struct.unpack("!Q", _sock.recv(8))[0]
        # print("got path", rel_path)
        recv_file(abs_path, f_size, _sock)
        # print("received file", f_size)


def send_path(sock: socket.socket, path: Path, parent, end_with='/'):
    path = path.relative_to(parent)
    path_len = struct.pack('!I', len(str(path) + end_with))
    sock.send(path_len)
    sock.send((str(path.as_posix()) + end_with).encode())
    return str(path.as_posix()) + end_with


def send_file(sock: socket.socket, path: Path):
    # progress = tqdm.tqdm(
    #     range(path.stat().st_size),
    #     desc=f"sending {path.relative_to(parent.parent)}",
    #     unit='B',
    #     unit_scale=True,
    #     unit_divisor=1024
    # )
    s = send_path(sock, path, parent.parent, '')
    sock.send(struct.pack('!Q', path.stat().st_size))
    with path.open('rb') as f:
        f_read = f.read
        while True:
            chunk = memoryview(f_read(chunk_size))
            if not chunk:
                break
            sock.send(chunk)
            # progress.update(len(chunk))
    # progress.close()
    return s


def send_directory(sock: socket.socket, path: Path):

    item_iter = path.iterdir()
    stack = [item_iter,]
    while len(stack):
        dir_iter = stack.pop()
        for item in dir_iter:
            if item.is_file():
                send_file(sock, item)
            elif item.is_dir():
                if not any(item.iterdir()):
                    print("sending empty dir:", send_path(sock, item, parent.parent))
                    continue
                stack.append(item.iterdir())


def initiate():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 8090))
    print('connected')
    with sock:
        s = time.monotonic()
        send_directory(sock, parent)
        e = time.monotonic()

    print(e - s, "sec")

    print("sent directory")


if __name__ == "__main__":
    # sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # sock.bind(("localhost", 8090))
    # sock.listen(1)
    # ali_sock, ali_address = sock.accept()
    # print("> connected..")
    # recv_dir(ali_sock)
    ...
chunk_size = 1024
parent = Path("C:\\Users\\7862s\\Desktop\\python\\VideosSampleCode")


async def open_dir_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, dialogs.Dialog.open_directory_dialog_window)
    await result

    return result.result()
