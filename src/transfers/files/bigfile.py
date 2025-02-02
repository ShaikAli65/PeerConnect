import functools
import sys
from typing import BinaryIO, TextIO
from itertools import count
import mmap
import os
import asyncio
from collections.abc import Callable
from contextlib import aclosing
import struct
from src.avails import constants
from src.avails.exceptions import TransferIncomplete
from src.avails.wire import WireData
from src.transfers.files.receiver import recv_file_contents
from src.transfers.status import StatusIterator
from src.transfers.files._fileobject import FileItem, validatename
from src.transfers import thread_pool_for_disk_io

from src.transfers import TransferState
from src.transfers.files.sender import send_actual_file


CHUNK_SIZE = 30 * 1024 * 1024
CHUNK_ID = 0


async def bomb():
    raise Exception(
        "cancel all tasks in taskgroup"
    )  # change this to a exxception with specificity


class Sender:
    def __init__(
        self, file_path, peer_obj, transfer_id, status_iterator: StatusIterator
    ):
        self.file = FileItem(file_path, seeked=0)
        self.peer_obj = peer_obj
        self.id = transfer_id
        self.status_iter = status_iterator
        self.io_pairs = {}
        self.io_pair_index_generator = count()
        self.state = TransferState.PREPARING
        self.failed_chunks = []
        self.file_iterator = self.bigfile_chunk_generator()
        self.is_stop = False

    def bigfile_chunk_generator(self):
        size = self.file.size
        start = 0
        for id, i in enumerate(range(start, size, CHUNK_SIZE)):
            if len(self.failed_chunks):
                yield self.failed_chunks.pop(0)
            yield id, i, i + CHUNK_SIZE

    async def __aenter__(self):
        self.state = TransferState.CONNECTING
        self.status_iter.status_setup(
            f"[DIR] receiving file: {self.file}", self.file.seeked, self.file.size
        )
        self.task_group = asyncio.TaskGroup()
        await self.task_group.__aenter__()
        return self

    def add_connection(self, pair: tuple[Callable, Callable]):
        ind = next(self.io_pair_index_generator)
        self.io_pairs[ind] = pair
        self.task_group.create_task(self.send(pair, ind))

    async def send_file(self):
        async for update in self.status_iter:
            yield update

    async def cancel(self):
        self.is_stop = True
        self.state = TransferState.ABORTING
        await self.status_iter.stop(
            TransferIncomplete("User canceled the transfer")
        )  # review
        for task in self.task_group._tasks:
            # change this to a custom exception that specifically tells that this operation is cancelled
            task.set_exception(Exception())

    async def send(self, io_pair, index):
        sender, receiver = io_pair

        for big_chunk in self.file_iterator:
            id, start, end = big_chunk
            temp_file = FileItem(self.file.path, seeked=start)
            temp_file.size = end

            file_send_request = WireData(
                header="deside something",
                file_id=id,
            )

            raw_bytes = bytes(file_send_request)
            data_size = struct.pack("!I", len(raw_bytes))

            try:
                sender(data_size)
                sender(raw_bytes)
                async with aclosing(
                    send_actual_file(sender, temp_file)
                ) as chunk_sender:
                    async for seeked in chunk_sender:
                        if self.is_stop:
                            break
                        self.status_iter.update_status(
                            seeked
                        )  # updating even for a small chunk
            finally:
                if (
                    not temp_file.seeked == temp_file.size
                ):  # a case when transfer is returned before completely sending the file
                    # adding the failed chunk to failed list so that the another pair get associated for this chunk
                    self.failed_chunks.append(big_chunk)
                    del self.io_pairs[index]
                    break

    async def continue_transfer(self):
        return

    async def __aexit__(self, exec_type, exec_val, exec_tb):
        if exec_type == TransferIncomplete:
            self.task_group.create_task(bomb())
        try:
            await self.task_group.__aexit__(None, None, None)
        except* Exception as e:
            if not self.is_stop:
                self.state = TransferState.PAUSED
                raise TransferIncomplete(
                    "Error in sending contents from sender receiver pair"
                ) from e.exceptions[0]
            raise e.exceptions[0]

        return False


if sys.platform == "win32":
    # must be fully qualified name  no reletive paths
    def windows_merge(fsrc: TextIO, fdst: TextIO):
        src_size = os.path.getsize(fsrc.name)
        dst_size = os.path.getsize(fdst.name)

        # Align to allocation granularity (64KB on Windows)
        allocation_granularity = mmap.ALLOCATIONGRANULARITY
        aligned_offset = (dst_size // allocation_granularity) * allocation_granularity
        map_size = dst_size + src_size - aligned_offset

        # Extend destination file
        fdst.truncate(dst_size + src_size)

        # Memory map source file
        src_map = mmap.mmap(fsrc.fileno(), src_size, access=mmap.ACCESS_READ)

        try:
            # Memory map destination file
            dst_map = mmap.mmap(
                fdst.fileno(),
                map_size,
                access=mmap.ACCESS_WRITE,
                offset=aligned_offset,
            )

            # Calculate write position relative to mapped region
            write_pos = dst_size - aligned_offset
            dst_map[write_pos : write_pos + src_size] = src_map[:]
        finally:
            src_map.close()
            dst_map.close()

    merge = windows_merge

else:
    # must be fully qualified name  no reletive paths
    def others_merge(fsrc: BinaryIO, fdst: BinaryIO):
        os.sendfile(fsrc.fileno(), fdst.fileno(), 0, os.path.getsize(fdst.name))

    merge = others_merge


async def merge_all_and_delete(final_file: FileItem, parts: dict[int, FileItem]):
    files = sorted(parts.items(), key=lambda x: x[0])

    with open(constants.PATH_DOWNLOAD / final_file.path, "ab") as final:
        final.seek(0)

        async def asyncify_merge(curr: BinaryIO):
            await asyncio.get_running_loop().run_in_executor(
                thread_pool_for_disk_io, functools.partial(merge, final, curr)
            )

        for ind, file in files:
            with open(constants.PATH_DOWNLOAD / file.path, "rb") as curr:
                await asyncify_merge(curr)  # Append file2 to file1


class Receiver:
    def __init__(
        self, file, peer_obj, transfer_id, status_iterator: StatusIterator
    ) -> None:
        self.file = FileItem(file, seeked=0)
        self.peer_obj = peer_obj
        self.id = transfer_id
        self.status_iter = status_iterator
        self.io_pairs = {}
        self.parts = {}
        self.state = TransferState.PREPARING
        self.io_pair_index_generator = count()
        self.task_group = asyncio.TaskGroup()
        self.is_stop = False

    def add_connectiond(self, io_pair):
        ind = next(self.io_pair_index_generator)
        self.io_pairs[ind] = io_pair
        self.task_group.create_task(self.recv(io_pair, ind))

    async def __aenter__(self):
        self.status_iter.status_setup(
            f"[DIR] receiving file: {self.file}", self.file.seeked, self.file.size
        )
        await self.task_group.__aenter__()
        return self

    async def recv_file(self):
        async for status in self.status_iter:
            yield status

    async def recv(self, io_pair: tuple[Callable, Callable], ind: int):
        sender, receiver = io_pair

        while self.is_stop:
            data_length = struct.unpack("!I", await receiver(4))[0]
            data = WireData.load_from(await receiver(data_length))

            file_id = data.body["file_id"]
            new_file = FileItem(
                self.file.path.stem + file_id + constants.FILE_ERROR_EXT, seeked=0
            )

            validatename(new_file, constants.PATH_DOWNLOAD)
            try:
                async for update in recv_file_contents(
                    receiver,
                    FileItem(constants.PATH_DOWNLOAD / new_file.path, seeked=0),
                ):
                    self.status_iter.update_status(update)
            finally:
                if new_file.seeked < CHUNK_SIZE:
                    # this chunk is not completelty done
                    new_file.path.unlink()  # delete the incomplete file
                    return
            self.parts[file_id] = new_file

    async def continue_recv(self):
        return

    async def cancel(self):
        self.is_stop = True
        self.state = TransferState.ABORTING
        await self.status_iter.stop(
            TransferIncomplete("User canceled the transfer")
        )  # review
        for task in self.task_group._tasks:
            task.set_exception(Exception())

    async def __aexit__(self, e_type, e_val, e_tb):
        # todo check for raised errors
        if e_type == TransferIncomplete:
            self.task_group.create_task(bomb())

        try:
            await self.task_group.__aexit__(None, None, None)
        except* Exception as e:
            if not self.is_stop:
                raise TransferIncomplete(
                    "Error in sending contents from sender receiver pair"
                ) from e.exceptions[0]
            raise e.exceptions[0]

        await merge_all_and_delete(self.file, self.parts)
