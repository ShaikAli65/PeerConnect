import asyncio
import itertools
import struct
from pathlib import Path
from typing import Iterator, NamedTuple

from src.core.transfers import FileItem, TransferState

END_DIR_WITH = '/'


class Ack(NamedTuple):
    status: bool


class DirectorySender:
    def __init__(self, item_queue, ack_queue, send_func, root_path):
        self.item_queue = item_queue
        self.ack_queue = ack_queue
        self.send_func = send_func
        self.root_path = root_path

    async def _send_path(self, path: Path, end_with):
        path = path.relative_to(self.root_path)
        path_len = struct.pack('!I', len(str(path) + end_with))
        await self.send_func(path_len)
        await self.send_func((str(path.as_posix()) + end_with).encode())
        return str(path.as_posix()) + end_with

    async def _send_file_item(self, file_item: FileItem):
        ...


class DirectorySenderManager:
    def __init__(self, root_path, transfer_id, send_func):
        """
        Args:
            root_path(Path): root path to read from and start the transfer
            transfer_id(str): transfer id that synchronized both sides
            send_func(Callable[[bytes],Coroutine[None, None, None]): function to call upon to send file data when ready
        """
        self.state = TransferState.PREPARING
        self.root_path = root_path
        self.current_file = None
        self.id = transfer_id
        self.send_func = send_func
        self.item_queue = asyncio.Queue[Path | FileItem]()
        self.ack_queue = asyncio.Queue[Ack]()

    def start(self):
        stack = [self.root_path]
        while len(stack):
            dir_iter = stack.pop()

            for item in (dir_iterator := dir_iter.iterdir()):

                item_to_put_in_queue = None
                if item.is_file():
                    item_to_put_in_queue = FileItem(path=item, seeked=0)
                elif item.is_dir():
                    if not any(item.iterdir()):
                        item_to_put_in_queue = item
                    else:
                        stack.append(item.iterdir())

                if not self.item_queue.full():
                    self.item_queue.put_nowait(item_to_put_in_queue)
                    continue

                    #
                    # if not any(item.iterdir()):
                    #     item
                    #     print("sending empty dir:", send_path(sock, item, self.root_path.parent))
                    #     continue

    def _process_acks(self):
        while True:
            if not self.ack_queue.empty():
                ack = self.ack_queue.get()

    def stop(self):
        pass

    def pause(self):
        self.dir_iterator = itertools.chain([self.current_file], self.dir_iterator)

    def continue_transfer(self):
        pass
