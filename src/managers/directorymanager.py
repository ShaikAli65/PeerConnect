import asyncio
import itertools
import os
import pathlib
import socket
import struct
from pathlib import Path

import tqdm

from src.avails import DataWeaver, TransfersBookKeeper, Wire, WireData, connect, const, get_dialog_handler, use
from src.core import get_this_remote_peer, peers
from src.core.connections import Connector
from src.core.handles import TaskHandle
from src.core.transfers import FileItem, HEADERS, TransferState

END_DIR_WITH = '/'

transfers_book = TransfersBookKeeper()


async def open_dir_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, get_dialog_handler().open_directory_dialog_window)
    return await result


async def new_directory_send_transfer(signal_data: DataWeaver):
    print("processing")
    print(signal_data)
    dir_path = await open_dir_selector()
    if not dir_path:
        print("cancelling dir send request, no directory specified")
        return
    dir_path = Path(dir_path)
    transfer_id = transfers_book.get_new_id()
    dir_recv_signal_packet = WireData(
        header=HEADERS.CMD_RECV_DIR,
        msg_id=get_this_remote_peer().peer_id,
        transfer_id=transfer_id
    )
    remote_peer = await peers.get_remote_peer_at_every_cost(signal_data.peer_id)
    if not remote_peer:
        raise Exception(f"cannot find remote peer object for given id{signal_data.peer_id}")

    connection = await Connector.get_connection(remote_peer)
    sender = DirectorySender(dir_path, transfer_id,)


def new_directory_receive_request(request_packet: WireData):
    transfer_id = request_packet.body['transfer_id']


class DirectorySender:
    def __init__(self, root_path, transfer_id, send_func):
        """
        Args:
            root_path(Path): root path to read from and start the transfer
            transfer_id(str): transfer id that synchronized both sides
            send_func(Callable[[bytes],Coroutine[None, None, None]): function to call upon to send file data when ready
        """
        self.state = TransferState.PREPARING
        self.root_path = root_path
        self.dir_iterator = self.root_path.rglob('*')
        self.current_file = None
        self.id = transfer_id
        self.send_func = send_func

    async def start(self):

        progress = tqdm.tqdm(

        )

        stack = [self.dir_iterator]
        while len(stack):
            for item in stack.pop():
                file_items = []
                empty_dirs = []

                if item.is_file():
                    file_item = FileItem(path=item, seeked=0)
                elif item.is_dir():
                    if not any(item.iterdir()):
                        print("sending empty dir:", send_path(sock, item, self.root_path.parent))
                        continue
                    stack.append(item.iterdir())

    def stop(self):
        pass

    def pause(self):
        self.dir_iterator = itertools.chain([self.current_file], self.dir_iterator)

    def continue_transfer(self):
        pass


class DirectoryReceiver:
    def __init__(self):
        self.state = TransferState.PREPARING

    async def start(self):
        pass

    def stop(self):
        pass

    def continue_transfer(self):
        pass


@use.NotInUse
class DirectoryTaskHandle(TaskHandle):
    chunk_size = 1024
    end_dir_with = '/'

    def __init__(self, handle_id, dir_path, dir_id, connection: connect.Socket, function_code):
        super().__init__(handle_id)
        self.dir_path = dir_path
        self.dir_id = dir_id
        self.socket = connection
        self.function_code = function_code
        self.dir_iterator = self.dir_path.rglob('*')
        self.current_file = None

    def start(self):
        # use.echo_print('starting ', self.function_code, 'with', self.socket)
        ...

    def pause(self):
        self.dir_iterator = itertools.chain([self.current_file], self.dir_iterator)

    def __send_dir(self):
        for item in self.dir_iterator:
            if item.is_file():
                if not self.__send_file(item):
                    self.pause()
                    break
            elif item.is_dir():
                if not any(item.iterdir()):
                    use.echo_print("sending empty dir:",
                                   self.__send_path(item, self.dir_path.parent, self.end_dir_with))
                    continue

    def __send_file(self, item_path: pathlib.Path):
        s = self.__send_path(item_path, self.dir_path.parent, None)
        self.socket.send(struct.pack('!Q', item_path.stat().st_size))
        with item_path.open('rb') as f:
            f_read = f.read
            while True:
                chunk = memoryview(f_read(self.chunk_size))
                if not chunk:
                    break
                self.socket.send(chunk)
                # progress.update(len(chunk))
        # progress.close()
        return s

    def __send_path(self, path: Path, parent, end_with):
        path = path.relative_to(parent)
        final_path = (path.as_posix() + end_with).encode(const.FORMAT)
        Wire.send(self.socket, final_path)
        return final_path.decode(const.FORMAT)

    def recv_dir(self):
        while True:
            path = Wire.receive(self.socket)
            if not path:
                print("I am done")
                return
            rel_path = path.decode(const.FORMAT)
            abs_path = Path(const.PATH_DOWNLOAD, rel_path[:-1])
            if rel_path.endswith("/"):
                os.makedirs(abs_path, exist_ok=True)
                continue
            os.makedirs(abs_path.parent, exist_ok=True)
            # print("parent", abs_path.parent)
            # print("got path", rel_path)
            self.recv_file(abs_path)
            # print("received file", f_size)

    def recv_file(self, file_path):
        size = self.socket.recv(8)
        file_item = FileItem(file_path, 0)

        ...

    def cancel(self):
        ...

    def status(self):
        ...

    def chain(self):
        ...


DOWNLOADS_DIR = "./down"
CHUNK_SIZE = 1024


def recv_something(_sock: socket.socket):
    lenght = struct.unpack("!I", _sock.recv(4))[0]
    data = _sock.recv(lenght)
    return data.decode()


def recv_file(_fpath: Path, _size: int, _sock: socket.socket):
    with open(_fpath, "wb") as file:
        while _size > 0:
            data = _sock.recv(min(CHUNK_SIZE, _size))
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
    stack = [item_iter, ]
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
        send_directory(sock, parent)
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
