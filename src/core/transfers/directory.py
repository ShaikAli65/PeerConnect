import asyncio
import os
import struct
from pathlib import Path
from typing import NamedTuple

from src.core.transfers import FileItem, TransferState, fileobject, recv_actual_file, recv_file_setup

END_DIR_WITH = '/'


class Ack(NamedTuple):
    status: bool
    seeked: int


class DirectorySender:
    def __init__(self, item_queue, ack_queue, send_func, root_path):
        self.item_queue: asyncio.Queue[FileItem | Path] = item_queue
        self.ack_queue: asyncio.Queue[Ack] = ack_queue
        self.send_func = send_func
        self.root_path: Path = root_path

    async def initiate(self):
        while True:
            item = await self.item_queue.get()
            if isinstance(item, FileItem):
                await self.send_func(b'\x00')
                ack = await self._send_file_item(item)
            else:
                await self.send_func(b'\x01')
                ack = await self._send_path(item, END_DIR_WITH)

            self.ack_queue.put_nowait(ack)

    async def _send_path(self, path: Path, end_with):
        path = path.relative_to(self.root_path)
        path_len = struct.pack('!I', len(str(path) + end_with))
        await self.send_func(path_len)
        await self.send_func((str(path.as_posix()) + end_with).encode())
        return str(path.as_posix()) + end_with

    async def _send_file_item(self, file_item: FileItem):
        send_progress = await fileobject.send_file_setup(self.send_func, file=file_item)
        await fileobject.send_actual_file(self.send_func, file_item, send_progress)
        send_progress.close()


class DirectoryReceiver:
    ...


class DirectorySenderManager:
    def __init__(self, root_path, transfer_id, send_func, buffer_items):
        """
        Args:
            root_path(Path): root path to read from and start the transfer
            transfer_id(str): transfer id that synchronized both sides
            send_func(Callable[[bytes],Coroutine[None, None, None]): function to call upon to send file data when ready
            buffer_items(int): maximum no of items to buffer for confirmations from sender object
        """
        self.state = TransferState.PREPARING
        self.root_path = root_path
        self.current_file = None
        self.id = transfer_id
        self.send_func = send_func
        self.proceed_flag = asyncio.Event()
        self.item_queue = asyncio.Queue[Path | FileItem](maxsize=buffer_items)
        self.ack_queue = asyncio.Queue[Ack](maxsize=buffer_items)
        self.transferred_directory_paths = []
        self.dir_iterator = self.root_path.rglob('*')
        self.to_be_acked_items = []
        self.current_dir_sending_state_info = None

    async def start(self):
        for item in self.dir_iterator:
            if self.proceed_flag.is_set():
                break

            if item.is_file():
                item_to_put_in_queue = FileItem(path=item, seeked=0)
            elif item.is_dir():
                item_to_put_in_queue = item
            else:
                continue

            if not self.item_queue.full():
                self.item_queue.put_nowait(item_to_put_in_queue)
                self.to_be_acked_items.append(item_to_put_in_queue)
                continue

            await self._process_acks()

            await self.item_queue.put(item_to_put_in_queue)

    async def _process_acks(self):
        while True:
            if not self.ack_queue.empty():
                ack = await self.ack_queue.get()
                print("received ack ",ack)
            else:
                break

    def stop(self):
        pass

    def pause(self):
        pass

    def continue_transfer(self):
        pass


class DirectoryReceiverManager:
    def __init__(self, transfer_id, recv_func, download_path):
        self.id = transfer_id
        self.recv_func = recv_func
        self.stop_flag = asyncio.Event()
        self.download_path = download_path

    async def start(self):
        while True:
            code = await self.recv_func(1)

            if code == b'\x00':
                await self._recv_file()
            elif code == b'\x01':
                await self._recv_path()

    async def _recv_path(self):
        rel_path = struct.unpack('!I', await self.recv_func(4))[0]
        abs_path = Path(self.download_path, rel_path)
        os.makedirs(abs_path.parent, exist_ok=True)

    async def _recv_file(self):
        file_item, progress = await recv_file_setup(self.recv_func, self.download_path)
        await recv_actual_file(self.stop_flag.is_set, self.recv_func, file_item, progress)

    async def stop(self):
        pass

    async def pause(self):
        pass

    async def continue_transfer(self):
        pass
