import asyncio
import functools
import os
import struct
from contextlib import aclosing, contextmanager

from src.avails import const, use
from src.avails.exceptions import CancelTransfer, InvalidStateError, TransferIncomplete
from src.transfers import TransferState, thread_pool_for_disk_io
from src.transfers._logger import logger as _logger
from src.transfers.abc import AbstractReceiver, CommonAExitMixIn, CommonExceptionHandlersMixIn
from src.transfers.files._fileobject import FileItem, calculate_chunk_size, validatename


class Receiver(CommonAExitMixIn, CommonExceptionHandlersMixIn, AbstractReceiver):
    version = const.VERSIONS['FO']

    def __init__(self, peer_obj, file_id, download_path, status_updater):
        self.recv_files_task = None
        self.state = TransferState.PREPARING
        self.peer = peer_obj
        self._file_id = file_id
        self.connection_wait = asyncio.get_event_loop().create_future()
        self.download_path = download_path
        self._current_file = None
        self.to_stop = False  # only set when Receiver.cancel is called
        self.file_items = []
        self.send_func = None
        self.recv_func = None
        self.status_updater = status_updater
        self._expected_errors = set()

    async def recv_files(self):
        """Start receiving files
        Not reentrant, see AbstractTransferHandle.continue_transfer for that behaviour
        """

        self.recv_files_task = asyncio.current_task()

        _logger.debug(f"{self._log_prefix} changing state to CONNECTING")
        self.state = TransferState.CONNECTING
        await self.connection_wait

        _logger.debug(f"{self._log_prefix} changing state to RECEIVING")
        self.state = TransferState.RECEIVING

        while True:
            if not await self._should_proceed():
                break
            async with aclosing(self._recv_file_once()) as loop:
                async for _ in loop:
                    yield _

        self.state = TransferState.COMPLETED
        _logger.info(f'completed transfer: {self.file_items}')

    async def _should_proceed(self):
        if self.to_stop:
            return b''

        try:
            what = await self.recv_func(1)
            # check again, what if context switch happened
            if self.to_stop:
                return b''
        except Exception as e:
            self.handle_exception(e)
        else:
            if what == b'\x00':
                _logger.info(
                    f"{self._log_prefix} received end of transfer signal, finalizing file recv loop, changing state to COMPLETED")
                return b''

            return what

    async def _recv_file_once(self):
        try:
            self._current_file = await self._recv_file_item()
        except Exception as exp:
            self.handle_exception(exp)

        self.file_items.append(self._current_file)
        if self._current_file.size <= 0:
            self._current_file.path.touch(exist_ok=True)
            return

        async with aclosing(self._receive_single_file()) as file_receiver:
            async for _ in file_receiver:
                yield

    async def _recv_file_item(self):
        try:
            file_item_size = await use.recv_int(self.recv_func)
        except ValueError as ve:
            raise TransferIncomplete from ve
        try:
            raw_file_item = await self.recv_func(file_item_size)
        except OSError as oe:
            raise TransferIncomplete from oe
        else:
            file_item = FileItem.load_from(raw_file_item, self.download_path)
            return file_item

    async def _receive_single_file(self):
        validatename(file_item=self.current_file, root_path=self.download_path)
        receiver = recv_file_contents(self.recv_func, self.current_file)
        self.status_updater.status_setup(self._status_string_prefix, self.current_file.seeked, self.current_file.size)

        status_updater = self.status_updater.update_status

        async with aclosing(receiver) as file_receiver:
            try:
                async for received_len in file_receiver:
                    status_updater(received_len)
                    yield
                    if self.to_stop:
                        break
            except Exception as exp:
                # raise early
                self.handle_exception(exp)

        if self.current_file.seeked < self.current_file.size:
            if self.to_stop is True:
                # if we are expected to finalize then no need to raise TransferIncomplete
                return

            # we don't reach to this point (mostly)
            raise TransferIncomplete("exiting before completion of transfer")

    async def continue_transfer(self):
        if not self.state == TransferState.PAUSED or self.to_stop is True:
            raise InvalidStateError(f"{self.state=}, {self.to_stop=}")

        self.recv_files_task = asyncio.current_task()

        _logger.debug(f'FILE[{self._file_id}] changing state to receiving')
        self.state = TransferState.RECEIVING
        await self.connection_wait

        try:
            # synchronizing last received file seek
            await self.send_func(struct.pack('!Q', self.current_file.seeked))
        except Exception as exp:
            self.handle_exception(exp)

        while True:
            if not self._should_proceed():
                break

            # getting remaining files
            async with aclosing(self._recv_file_once()) as file_receiver:
                async for items in file_receiver:
                    yield items

    def connection_made(self, sender, receiver):
        self.connection_wait.set_result((sender, receiver))
        self.send_func = sender
        self.recv_func = receiver

    async def cancel(self):
        if self.state is not TransferState.RECEIVING:
            raise InvalidStateError(f"{self.state}")

        self.to_stop = True
        self._expected_errors.add(ct := CancelTransfer())
        self.recv_files_task.set_exception(ct)
        await self.recv_files_task

    @property
    def _status_string_prefix(self):
        return f"[FILE] {self.current_file}"

    @property
    def current_file(self):
        return self._current_file

    @property
    def id(self):
        return f"{self.peer.peer_id} {self._file_id}"


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
    mode = (
        "xb" if file_item.seeked == 0 else "rb+"
    )  # Create a new file or open for reading and writing
    # Check for the existence of the file for resuming
    # A reason for going with more specific modes like xb or rb+ rather than using "w" modes
    # by any chance if the file_item is misconfigured and the file held by file_item is important
    # all the contents are cleared

    if file_item.seeked > 0 and not os.path.exists(file_item.path):
        print(f"File {file_item.path} not found for resuming transfer.")  # debug
        raise FileNotFoundError(
            f"File {file_item.path} not found for resuming transfer."
        )

    chunk_size = chunk_size or calculate_chunk_size(file_item.size)
    remaining_bytes = file_item.size
    loop = asyncio.get_running_loop()

    with open(file_item.path, mode) as fd:
        fd.seek(file_item.seeked)
        async_writer = functools.partial(loop.run_in_executor, th_pool, fd.write)
        remaining_bytes -= file_item.seeked
        yield chunk_size, file_item.size, async_writer, remaining_bytes
