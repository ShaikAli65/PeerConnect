import asyncio
import functools
import os
import struct
from asyncio import CancelledError
from contextlib import aclosing, contextmanager

from src.avails import const, use
from src.avails.exceptions import TransferIncomplete
from src.transfers import TransferState, thread_pool_for_disk_io
from src.transfers.files._fileobject import FileItem, calculate_chunk_size, validatename
from src.transfers.files._logger import logger as _logger


class Receiver:
    version = const.VERSIONS['FO']

    def __init__(self, peer_id, file_id, download_path, status_updater):
        self.state = TransferState.PREPARING
        self.peer_id = peer_id
        self._file_id = file_id
        self.connection_wait = asyncio.get_event_loop().create_future()
        self._log_prefix = f'FILE[{self.peer_id}]'
        self.download_path = download_path
        self.current_file = None
        self.to_stop = False
        self.file_items = []
        self.send_func = None
        self.recv_func = None
        self.status_updater = status_updater

    async def recv_files(self):
        self.state = TransferState.CONNECTING
        await self.get_connection()
        _logger.debug(f"{self._log_prefix} changing state to RECEIVING")
        self.state = TransferState.RECEIVING

        while await self._should_proceed():

            self.current_file = await self._recv_file_item()
            self.file_items.append(self.current_file)
            async with aclosing(self._receive_single_file()) as file_receiver:
                try:
                    async for received_size in file_receiver:
                        yield received_size

                        if self.to_stop:
                            break
                except TransferIncomplete:
                    _logger.error(f"{self._log_prefix} paused receiving, changing state to PAUSED", exc_info=True)
                    self.state = TransferState.PAUSED
                    raise

        self.state = TransferState.COMPLETED
        _logger.info(f'completed receiving: {self.file_items}')

    async def _should_proceed(self):

        if self.to_stop:
            return False

        what = await self.recv_func(1)

        # check again, what if context switch happened
        if self.to_stop:
            _logger.debug(f"{self._log_prefix} found self.to_stop true, finalizing file recv loop")
            _logger.debug(f"{self._log_prefix} changing state to ABORTING")
            self.state = TransferState.ABORTING
            return False

        if not what:
            return False

        if not struct.unpack('?', what)[0]:
            _logger.info(
                f"{self._log_prefix} received end of transfer signal, finalizing file recv loop, changing state to COMPLETED")
            self.state = TransferState.COMPLETED
            return False

        return True

    async def _recv_file_item(self):
        try:
            file_item_size = await use.recv_int(self.recv_func)
            raw_file_item = await self.recv_func(file_item_size)
        except ValueError as ve:
            raise TransferIncomplete from ve
        except OSError as oe:
            raise TransferIncomplete from oe
        else:
            file_item = FileItem.load_from(raw_file_item, self.download_path)
            return file_item

    async def _receive_single_file(self):
        validatename(file_item=self.current_file, root_path=self.download_path)
        receiver = recv_file_contents(self.recv_func, self.current_file, )
        self.status_updater.status_setup(self._status_string_prefix, self.current_file.seeked, self.current_file.size)

        status_updater = self.status_updater.update_status
        async with aclosing(receiver) as file_receiver:
            async for received_len in file_receiver:
                status_updater(received_len)
                yield

    async def get_connection(self):
        self.send_func, self.recv_func = await self.connection_wait
        _logger.debug(f"got connection {self._file_id=}")

    async def continue_file_transfer(self):
        _logger.debug(f'FILE[{self._file_id}] changing state to receiving')
        self.state = TransferState.RECEIVING
        await self.get_connection()
        seeked_ptr = struct.pack('!Q', self.current_file.seeked)

        # synchronizing last received file seek
        self.send_func(seeked_ptr)

        # receiving broken transfer file contents
        async with aclosing(self._receive_single_file()) as fr:
            async for received_len in fr:
                yield self.current_file, received_len

        # getting remaining files
        async with aclosing(self.recv_files()) as file_receiver:
            async for items in file_receiver:
                yield items

    def connection_arrived(self, connection):
        self.connection_wait.set_result(connection)

    @property
    def _status_string_prefix(self):
        return f"[FILE] {self.current_file}"

    @property
    def id(self):
        return self._file_id


async def recv_file_contents(recv_function, file_item, *, chunk_size=None):
    """Receive a file over a network connection and write it to disk.

    if ``FileItem.seeked`` attribute is non-zero then the file at ``file_item.path`` is checked for existence
    if not found then FileNoFoundError is raised.
    if found then opened in **rb+** mode

    Args:
        recv_function (Callable): A function to receive data.
        file_item (FileItem): An object containing file metadata.
        chunk_size(int): The size of each chunk passed into ``recv_function``
        # progress (ProgressTracker): An object to track progress of file writing.
        # stopping_flag(Callable): gets called to check when looping over byte chunks received from ``recv_function``

    Raises:
        FileNotFoundError: If ``file_item.path`` is not found.
        TransferIncomplete: if anything goes wrong and file transfer is incomplete

    Yields:
        int: updated remaining file size to be received
    """

    with _setup_transfer(chunk_size, file_item) as t:  # noqa
        chunk_size, file_size, f_writer, remaining_bytes = t

        while remaining_bytes > 0:
            data = await recv_function(min(chunk_size, remaining_bytes))
            if not data:
                break

            await f_writer(data)  # Attempt to write data to file

            remaining_bytes -= len(data)
            file_item.seeked += len(data)
            yield file_size - remaining_bytes


@contextmanager
def _setup_transfer(chunk_size, file_item, *, th_pool=thread_pool_for_disk_io):
    mode = 'xb' if file_item.seeked == 0 else 'rb+'  # Create a new file or open for reading and writing
    # Check for the existence of the file for resuming

    if file_item.seeked > 0 and not os.path.exists(file_item.path):
        print(f"File {file_item.path} not found for resuming transfer.")  # debug
        raise FileNotFoundError(f"File {file_item.path} not found for resuming transfer.")

    chunk_size = chunk_size or calculate_chunk_size(file_item.size)
    remaining_bytes = file_item.size
    loop = asyncio.get_running_loop()

    with open(file_item.path, mode) as fd:
        fd.seek(file_item.seeked)
        async_writer = functools.partial(loop.run_in_executor, th_pool, fd.write)
        remaining_bytes -= file_item.seeked
        try:
            yield chunk_size, file_item.size, async_writer, remaining_bytes
        except Exception as e:
            _finalize_transfer(e, file_item)
            raise
    _finalize_transfer(None, file_item)


def _finalize_transfer(exp, file_item):
    if file_item.seeked < file_item.size:
        incomplete_transfer = TransferIncomplete(file_item)
        if exp:
            if isinstance(exp, CancelledError):
                raise exp from incomplete_transfer

            raise incomplete_transfer from exp
        else:
            raise incomplete_transfer
