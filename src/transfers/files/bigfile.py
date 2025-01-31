import asyncio
from collections.abc import Callable
from contextlib import aclosing
from src.avails.status import StatusIterator
from src.transfers.files._fileobject import FileItem

from src.transfers import TransferState
from src.transfers.files.sender import send_actual_file


CHUNK_SIZE = 30 * 1024 * 1024
CHUNK_ID = 0


class Sender:
    def __init__(
        self, file, peer_obj, transfer_id, status_iterator: StatusIterator, seeked=0
    ):
        self.file = FileItem(file, seeked=seeked)
        self.peer_obj = peer_obj
        self.id = transfer_id
        self.status_iter = status_iterator
        self.io_pairs = []
        self.state = TransferState.PREPARING
        self.task_group = asyncio.TaskGroup()

    def bigfile_chunk_generator(self):
        size = self.file.size
        start = 0
        for i in range(start, size, CHUNK_SIZE):
            yield i, i, i + CHUNK_SIZE

    def __enter__(self):
        self.status_iter.setup(
            f"[DIR] receiving file: {self.file}", self.file.seeked, self.file.size
        )
        self.file_iterator = self.bigfile_chunk_generator()
        self.next_pair = asyncio.Queue()
        return self

    def add_connection(self, pair: tuple[Callable, Callable]):
        self.io_pairs.append(pair)
        self.next_pair.put_nowait(pair)

    async def send(self, io_pair):
        sender, receiver = io_pair

        for chunk in self.file_iterator:
            id, start, end = chunk
            temp_file = FileItem(self.file.path, seeked=start)
            temp_file.size = end
            async with aclosing(send_actual_file(sender, temp_file)) as chunk_sender:

    async def send(self):
        for chunk in self.file_iterator:
            # ind = await asyncio.wait(*self.tasks, return_when=asyncio.FIRST_COMPLETED)
            io_pair = await self.next_pair.get()

            task = asyncio.create_task(self.send_big_chunk(chunk, io_pair))
            self.tasks[chunk[CHUNK_ID]] = task

    async def send_big_chunk(self, chunk, io_pair):
        sender, receiver = io_pair
        id, start, end = chunk
        temp_file = FileItem(self.file.path, seeked=start)
        temp_file.size = end
        try:
            async with aclosing(send_actual_file(sender, temp_file)) as chunk_sender:
                async for seeked in chunk_sender:
                    self.status_iter.update(seeked)  # updating for een smalll chunk

            await self.next_pair.put(io_pair)
        except:
            pass

    def __exit__(self, exec_type, exec_val, exec_tb):
        return False


class Receiver:
    pass
