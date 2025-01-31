import asyncio
import functools
import mmap
import struct
from contextlib import aclosing
from pathlib import Path

from src.avails import const, use
from src.avails.exceptions import CancelTransfer, InvalidStateError
from src.transfers import TransferState, thread_pool_for_disk_io
from src.transfers._logger import logger as _logger
from src.transfers.abc import AbstractSender, CommonAExitMixIn, CommonExceptionHandlersMixIn
from src.transfers.files._fileobject import FileItem, calculate_chunk_size


class Sender(CommonAExitMixIn, CommonExceptionHandlersMixIn, AbstractSender):
    version = const.VERSIONS['FO']
    timeout = const.DEFAULT_TRANSFER_TIMEOUT

    def __init__(self, peer_obj, transfer_id, file_list, status_updater):
        self.send_files_task = None
        self.state = TransferState.PREPARING
        self.file_list = [
            FileItem(Path(x), seeked=0) for x in file_list
        ]
        self._file_id = transfer_id
        self.peer_obj = peer_obj
        self.status_updater = status_updater
        self.to_stop = False
        self.socket = None
        self._current_file_index = 0
        self.send_func = None
        self.recv_func = None
        self._expected_errors = set()

    async def send_files(self):
        _logger.debug(f"{self._log_prefix} changing state to sending")
        self.state = TransferState.SENDING
        self.send_files_task = asyncio.current_task()

        for index in range(self._current_file_index, len(self.file_list)):

            if self.to_stop:
                break
            file_item = self.file_list[index]
            self._current_file_index = index
            await self._send_file_item(file_item)
            async with aclosing(self.send_one_file(file_item)) as loop:
                async for _ in loop:
                    yield _
            print("file sent", file_item)  # debug

        # end of transfer, signalling that there are no more files
        try:
            await self.send_func(b'\x00')
        except Exception as exp:
            self.handle_exception(exp)

        _logger.info(f"{self._log_prefix} sent final flag, completed sending")
        self.state = TransferState.COMPLETED

    async def send_one_file(self, file_item):
        try:
            self.status_updater.status_setup(
                prefix=f"sending: {file_item}",
                initial_limit=file_item.seeked,
                final_limit=file_item.size
            )
            updater = self.status_updater.update_status
            async with aclosing(send_actual_file(
                    self.send_func,
                    file_item,
            )) as send_file:
                async for seeked in send_file:
                    updater(seeked)
                    if self.to_stop:
                        break
                    yield seeked
        except Exception as exp:
            self.handle_exception(exp)

    async def _send_file_item(self, file_item):
        try:
            # a signal that says there is more to receive
            await self.send_func(b'\x01')
            file_object = bytes(file_item)
            file_packet = struct.pack('!I', len(file_object)) + file_object
            await self.send_func(file_packet)
        except Exception as exp:
            self.handle_exception(exp)

    async def continue_transfer(self):
        if not self.state == TransferState.PAUSED or self.to_stop is True:
            raise InvalidStateError(f"{self.state=}, {self.to_stop=}")

        _logger.debug(f'FILE[{self._file_id}] changing state to sending')
        self.state = TransferState.SENDING
        start_file = self.file_list[self._current_file_index]

        # synchronizing last file sent
        try:
            start_file.seeked = await use.recv_int(self.recv_func, use.LONG_INT)
        except ValueError as ve:
            self._raise_transfer_incomplete_and_change_state(ve)
        else:
            self.status_updater.status_setup(
                f"resuming file:{start_file}", start_file.seeked, start_file.size
            )

        # continuing with remaining transfer
        async with aclosing(self.send_files()) as file_sender:
            async for items in file_sender:
                yield items

    def attach_files(self, paths_list):
        self.file_list.extend(FileItem(Path(path), 0) for path in paths_list)

    async def cancel(self):
        if self.state is not TransferState.RECEIVING:
            raise InvalidStateError(f"{self.state}")

        self.to_stop = True
        self._expected_errors.add(ct := CancelTransfer())
        self.send_files_task.set_exception(ct)
        await self.send_files_task

    def connection_made(self, sender, receiver):
        self.send_func = sender
        self.recv_func = receiver

    @property
    def id(self):
        return self._file_id

    @property
    def current_file(self):
        return self.file_list[self._current_file_index]


async def send_actual_file(
        send_function,
        file,
        *,
        chunk_len=None,
        timeout=10,
        th_pool=thread_pool_for_disk_io,
):
    """Sends file to other end using ``send_function``

    Opens file in **rb** mode from the ``path`` attribute from ``file item``
    reads ``seeked`` attribute of ``file item`` to start the transfer from
    calls ``send_function`` and awaits on it every time this function tries to send a chunk
    if chunk_size parameter is not provided then calculates chunk size by calling ``calculate_chunk_size``

    Args:
        send_function(Callable): function to call when a chunk is ready
        file(FileItem): file to send
        chunk_len(int): length of each chunk passed into ``send_function`` for each call
        timeout(int): timeout in seconds used to wait upon send_function
        th_pool(ThreadPoolExecutor): thread pool executor to use while reading the file

    Yields:
        number indicating the file size sent
    """

    chunk_size = chunk_len or calculate_chunk_size(file.size)
    with open(file.path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as f_mapped:
            seek = file.seeked
            asyncify = functools.partial(
                asyncio.get_running_loop().run_in_executor,
                th_pool,
                f_mapped.__getitem__,
            )

            for offset in range(seek, file.size, chunk_size):
                chunk = await asyncify(slice(offset, offset + chunk_size))

                await asyncio.wait_for(send_function(chunk), timeout)
                seek += len(chunk)
                file.seeked = seek
                yield seek
