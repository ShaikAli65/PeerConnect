import asyncio
import struct
from pathlib import Path
from typing import NamedTuple

import tqdm
import umsgpack

from src.core.transfers import FileItem, TransferState, fileobject, recv_actual_file

END_DIR_WITH = '/'


class Ack(NamedTuple):
    status: bool
    seeked: int


def rename_directory_with_increment(root_path: Path, relative_path: Path):
    """
    Rename a directory under the root_path to avoid name collisions
    by appending a number in parentheses.

    Args:
        root_path (Path): The root directory.
        relative_path (Path): The relative path to the directory to rename.
    """
    abs_path = root_path / relative_path

    if not root_path.exists() or not root_path.is_dir():
        print(f"The directory {abs_path} does not exist or is not a directory.")
        return

    parent_dir = abs_path.parent
    base_name = abs_path.name
    new_name = base_name
    counter = 1

    # Increment the name if a conflict exists
    while (parent_dir / new_name).exists():
        new_name = f"{base_name}({counter})"
        counter += 1

    new_path = parent_dir / new_name
    new_path.mkdir(parents=True, exist_ok=True)

    return new_path


class DirectorySender:
    def __init__(self, item_queue, ack_queue, send_func, recv_func, root_path):
        self.item_queue: asyncio.Queue[FileItem | Path] = item_queue
        self.ack_queue: asyncio.Queue[Ack] = ack_queue
        self.send_func = send_func
        self.recv_func = recv_func
        self.root_path: Path = root_path

    async def initiate(self):
        while True:
            item = await self.item_queue.get()
            if isinstance(item, FileItem):
                await self.send_func(b'\x00')
                ack = await self._send_file_item(item)
                assert await self.recv_func(1) == b'\x00'
            else:
                await self.send_func(b'\x01')
                ack = await self._send_path(item, END_DIR_WITH)
                assert await self.recv_func(1) == b'\x01'

            await self.ack_queue.put(ack)

    async def _send_path(self, path: Path, end_with):
        path = path.relative_to(self.root_path)
        path_to_send = str(path)
        path_len = struct.pack('!I', len(path_to_send))
        await self.send_func(path_len)
        await self.send_func(path_to_send.encode())
        return path_to_send

    async def _send_file_item(self, file_item: FileItem):
        file_path = str(file_item.path.relative_to(self.root_path))
        file_packet = umsgpack.dumps((file_path, file_item.size))
        file_packet = struct.pack('!I', len(file_packet)) + file_packet

        await self.send_func(file_packet)  # possible : any sort of socket/connection errors

        send_progress = tqdm.tqdm(
            range(file_item.size),
            f" sending {file_item.name[:17] + '...' if len(file_item.name) > 20 else file_item.name} ",
            unit="B",
            unit_scale=True,
            unit_divisor=1024
        )
        # send_progress = await fileobject.send_file_setup(self.send_func, file=file_item)
        try:
            await fileobject.send_actual_file(self.send_func, file_item, send_progress)
        except ValueError as ve:
            import errno
            if ve.args[0] == "cannot mmap an empty file":
                pass

        send_progress.close()
        return file_item


class DirectoryReceiver:
    ...


class DirectorySenderManager:
    def __init__(self, root_path, transfer_id, send_func, recv_func, buffer_items=5):
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
        self.dir_sender = DirectorySender(
            self.item_queue,
            self.ack_queue,
            send_func,
            recv_func,
            self.root_path,
        )

    async def start(self):
        sender_task = asyncio.create_task(self.dir_sender.initiate())
        try:
            for item in self.dir_iterator:
                if self.proceed_flag.is_set():
                    break

                if item.is_file():
                    item_to_put_in_queue = FileItem(path=item, seeked=0)
                elif item.is_dir():
                    item_to_put_in_queue = item
                else:
                    continue
                print("putting item in queue", item_to_put_in_queue)

                if self.item_queue.full():
                    await self._process_acks()

                await self.item_queue.put(item_to_put_in_queue)
                self.to_be_acked_items.append(item_to_put_in_queue)
            await self._process_acks()
        finally:
            await sender_task

    async def _process_acks(self):
        while not self.proceed_flag.is_set():
            if not self.ack_queue.empty():
                ack = await self.ack_queue.get()
                # print("received ack ", ack)
            else:
                break

    def stop(self):
        pass

    def pause(self):
        pass

    def continue_transfer(self):
        pass


class DirectoryReceiveManager:
    def __init__(self, transfer_id, recv_func, send_func, download_path):
        self.id = transfer_id
        self.recv_func = recv_func
        self.send_func = send_func
        self.stop_flag = asyncio.Event()
        self.download_path = download_path

    async def start(self):
        while True:
            code = await self.recv_func(1)
            if code == b'':
                raise ConnectionResetError()

            if code == b'\x00':
                await self._recv_file()
            elif code == b'\x01':
                abs_path = await self._recv_path()
                abs_path.mkdir(parents=True, exist_ok=True)

            await self.send_func(code)

    async def _recv_path(self):
        rel_path_size = struct.unpack('!I', await self.recv_func(4))[0]
        rel_path = await self.recv_func(rel_path_size)
        abs_path = Path(self.download_path, rel_path.decode())
        return abs_path

    async def _recv_file(self):
        file_item_size = struct.unpack('!I', await self.recv_func(4))[0]
        file_path, file_size = umsgpack.loads(await self.recv_func(file_item_size))
        file_item = FileItem(Path(self.download_path, file_path), seeked=0)
        file_item.size = file_size
        progress = tqdm.tqdm(
            range(file_item.size),
            f"::receiving {file_item.name[:17] + '...' if len(file_item.name) > 20 else file_item.name} ",
            unit="B",
            unit_scale=True,
            unit_divisor=1024
        )
        await recv_actual_file(self.stop_flag.is_set, self.recv_func, file_item, progress)

    async def stop(self):
        pass

    async def pause(self):
        self.stop_flag.set()

    async def continue_transfer(self):
        self.stop_flag.clear()
        packed_seeked = struct.pack('!Q', self._current_item.seeked)
        await self.send_func(packed_seeked)

