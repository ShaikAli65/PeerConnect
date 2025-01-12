import asyncio
import itertools
import logging
import os
import pathlib
import struct
import traceback
from contextlib import aclosing, asynccontextmanager
from pathlib import Path

from src.avails import TransfersBookKeeper, Wire, WireData, connect, const, get_dialog_handler, use
from src.avails.events import ConnectionEvent
from src.avails.exceptions import TransferRejected
from src.core import Dock, get_this_remote_peer
from src.core.handles import TaskHandle
from src.core.transfers import FileItem, HEADERS, shorten_path
from src.core.transfers.directory import Receiver, Sender, \
    rename_directory_with_increment

transfers_book = TransfersBookKeeper()
_logger = logging.getLogger(__name__)


async def open_dir_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, get_dialog_handler().open_directory_dialog_window)  # noqa
    return await result


@asynccontextmanager
async def send_directory(remote_peer, dir_path):
    dir_path = Path(dir_path)
    transfer_id = transfers_book.get_new_id()
    dir_recv_signal_packet = WireData(
        header=HEADERS.CMD_RECV_DIR,
        peer_id=get_this_remote_peer().peer_id,
        transfer_id=transfer_id,
        dir_name=dir_path.name,
    )
    # from src.core.connections import Connector
    # connection = await Connector.get_connection(remote_peer)

    connection = await connect.connect_to_peer(
        remote_peer,
        to_which=connect.CONN_URI,
        timeout=1,
        retries=3
    )

    timeout = 5
    with connection:
        Wire.send(connection, bytes(dir_recv_signal_packet))
        await _get_confirmation(connection, timeout)

        sender = Sender(
            dir_path,
            transfer_id,
            connect.Sender(connection),
            connect.Receiver(connection),
        )

        _logger.info(f"sending directory: {dir_path} to {remote_peer}")
        async with aclosing(sender.start()) as s:
            yield s

        _logger.info(f"completed sending directory {dir_path} to {remote_peer}")


async def _get_confirmation(connection, timeout):
    try:
        confirmation = await asyncio.wait_for(connection.arecv(1), timeout=timeout)
        if confirmation == b'\x00':
            _logger.info("not sending directory, other end rejected")
            raise TransferRejected()
    except asyncio.TimeoutError:
        _logger.info(f"not sending directory, did not receive confirmation within {timeout} seconds")
        raise
    except ConnectionResetError:
        _logger.error("not sending directory", exc_info=True)
        raise


def pause_transfer(peer_id, transfer_id):
    transfer_handle = transfers_book.get_transfer(peer_id, transfer_id)
    if not transfer_handle:
        raise ValueError(f"transfer {transfer_id} not found")

    transfer_handle.pause()
    transfers_book.add_to_continued(peer_id, transfer_handle)


def DirConnectionHandler():
    async def handler(event: ConnectionEvent):
        transfer_id = event.handshake.body['transfer_id']
        transfer_id = event.handshake.peer_id + transfer_id

        connection = event.transport.socket
        dir_name = event.handshake.body['dir_name']
        dir_path = rename_directory_with_increment(const.PATH_DOWNLOAD, Path(dir_name))

        sender = connect.Sender(connection)
        recv = connect.Receiver(connection)
        receiver = Receiver(
            transfer_id,
            recv,
            sender,
            dir_path,
            const.TRANSFER_STATUS_FREQ
        )
        try:
            with connection:
                await sender(b'\x01')
                transfers_book.add_to_current(transfer_id, receiver)
                _logger.info(
                    f"receiving directory from {Dock.peer_list.get_peer(event.handshake.peer_id)}, saving at {shorten_path(dir_path, 20)}"
                )
                async with aclosing(receiver.start()) as receiver:
                    async for item in receiver:
                        print(item)

                _logger.info(f"directory received from {Dock.peer_list.get_peer(event.handshake.peer_id)}")
                transfers_book.add_to_completed(transfer_id, receiver)
        except Exception as e:
            print("*" * 80, e)
            traceback.print_exc()

    return handler


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
