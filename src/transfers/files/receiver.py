import asyncio
import struct
from contextlib import aclosing

from src import net
from src.avails import const
from src.avails.exceptions import InvalidStateError, TransferIncomplete
from src.transfers import HEADERS, TransferState, _logger
from src.transfers.abc import AbstractReceiver
from src.transfers.mixins import *
from ._fileio import FileItemWriter
from ._fileobject import FileItem, calculate_chunk_size, validatename


class Receiver(
    ExceptionRouterMixIn,  # keep at the top of the mro, cause calls to these methods are more
    # probably called only once or twice
    ControlMixIn,
    CommonAExitMixIn,
    # probably called on rare occasion
    CancelOperationMixIn,
    AbstractReceiver,
):
    version = const.VERSIONS["FO"]

    def __init__(self, peer_obj, file_id, download_path, status_updater):
        self.transfer_task = None
        self.state = TransferState.PREPARING
        self.peer = peer_obj
        self._transfer_id = file_id
        self.connection_wait = asyncio.get_event_loop().create_future()
        self.download_path = download_path
        self._current_file: FileItem | None = None
        self.should_stop = False  # only set when Receiver.cancel is called
        self.file_items = []
        self.net_sender = None
        self.net_receiver = None
        self.status_updater = status_updater
        self._expected_exps = set()
        self._on_completion_event = asyncio.Event()

    async def start_transfer(self):
        """Start receiving files
        Not reentrant, see AbstractTransferHandle.resume_transfer for that behaviour
        """

        self.transfer_task = asyncio.current_task()

        _logger.debug(f"{self._log_prefix} changing state to CONNECTING")
        self.state = TransferState.CONNECTING
        await self.connection_wait

        _logger.debug(f"{self._log_prefix} changing state to RECEIVING")
        self.state = TransferState.RECEIVING

        while True:
            if not await self._should_proceed():
                break
            try:
                async with aclosing(self._recv_file_once()) as loop:
                    async for _ in loop:
                        yield _
            finally:
                await self.status_updater.close()

        _logger.debug(f"{self._log_prefix} ACKing to transfer completion flag")
        await self.wrap_exp_handling(self.net_sender, HEADERS.END_OF_TRANSFER)
        self.state = TransferState.COMPLETED
        _logger.info(f"completed transfer: {len(self.file_items)=}")

    async def _should_proceed(self):
        if self.should_stop:
            return False

        what = await self.wrap_exp_handling(self.net_receiver, 1)
        # check again, what if context switch happened
        if self.should_stop:
            return False

        if what == HEADERS.END_OF_TRANSFER:
            _logger.info(
                f"{self._log_prefix} received end of transfer signal,"
                f" finalizing file recv loop, changing state to COMPLETED"
            )
            return False
        _logger.debug(f"receiving another file {what=}")
        return what

    async def _prepare_file_item(self):
        try:
            self._current_file = await self._recv_file_item()
        except Exception as exp:
            if self._current_file:
                exp.add_note(f"FILE ITEM path: {self._current_file.path}")

            self.handle_exception(exp)
        _logger.debug(f"{self._log_prefix} file item received, {self._current_file}")
        self.file_items.append(self._current_file)
        if self._current_file.size == 0:
            self._current_file.path.touch(exist_ok=True)
            return False

        validatename(file_item=self._current_file, root_path=self.download_path)
        return True

    async def _recv_file_once(self):
        if await self._prepare_file_item() is False:
            return

        self.status_updater.status_setup(
            self._status_string_prefix,
            initial_limit=self._current_file.seeked,
            final_limit=self._current_file.size,
        )

        f_writer = FileItemWriter(self._current_file)
        async with aclosing(self._receive_single_file(f_writer)) as file_receiver:
            try:
                _logger.debug(
                    f"{self._log_prefix} receiving file data, {self._current_file}, {f_writer=}"
                )
                async for chunk_len in file_receiver:
                    await self.status_updater.write_update(chunk_len)
                    yield chunk_len
            finally:
                self._current_file.seeked = f_writer.seek_pos

        _logger.debug(f"{self._log_prefix} completed receiving file data, {f_writer=}")

    async def _recv_file_item(self):
        try:
            file_item_size = await net.recv_int(self.net_receiver)
        except ValueError as ve:
            raise TransferIncomplete from ve
        try:
            raw_file_item = await self.net_receiver(file_item_size)
        except OSError as oe:
            raise TransferIncomplete from oe
        else:

            file_item = FileItem.load_from(raw_file_item, self.download_path)
            return file_item

    async def _receive_single_file(self, f_writer):
        """Receive a file over a network connection and write it to disk.

        if ``FileItem.seeked`` attribute is non-zero then the file at ``file_item.path`` is checked for existence
        if not found then FileNoFoundError is raised.
        if found then opened in **rb+** mode

        Args:
            f_writer (AbstractReader): Writer to write data.

        Raises:
            FileNotFoundError: If ``file_item.path`` is not found.

        Yields:
            size of chunk written
        """

        receiver = net.ChunkedReceiver(
            self.net_receiver,
            f_writer.size,
            calculate_chunk_size(f_writer.size),
        )
        try:
            async with f_writer.start_writing(), aclosing(receiver):
                async for data in receiver:
                    yield await f_writer.write(data)
        except Exception as exp:
            self.handle_exception(exp)

    async def resume_transfer(self):
        if not self.state == TransferState.PAUSED or self.should_stop is True:
            raise InvalidStateError(f"{self.state=}, {self.should_stop=}")
        self.transfer_task = asyncio.current_task()

        self.state = TransferState.CONNECTING
        await self.connection_wait  # wait until we get a connection

        _logger.debug(f"FILE[{self._transfer_id}] changing state to receiving")
        self.state = TransferState.RECEIVING

        # synchronizing last received file seek
        s = struct.pack("!Q", self.current_file.seeked)
        await self.wrap_exp_handling(self.net_sender, s)

        while True:
            if not self._should_proceed():
                break

            # getting remaining files
            async with aclosing(self._recv_file_once()) as file_receiver:
                async for items in file_receiver:
                    yield items

    def connection_made(self, connection):
        _logger.debug(f"{self._log_prefix} connection made, {connection}")
        self.connection_wait.set_result(connection)
        self.net_sender = connection.send
        self.net_receiver = connection.recv

    def resume(self):
        if self.state is not TransferState.PAUSED:
            return

        self.state = TransferState.RECEIVING
        self.net_sender.resume()
        self.net_receiver.resume()

    @property
    def _status_string_prefix(self):
        return f"[FILE] {self.current_file}"

    @property
    def current_file(self):
        return self._current_file

    @property
    def id(self):
        return self._transfer_id

    @property
    def done(self):
        return self._on_completion_event
