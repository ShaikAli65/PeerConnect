import asyncio
import struct
from contextlib import aclosing

from src import net
from src.avails import const
from src.avails.exceptions import InvalidStateError
from src.transfers import HEADERS, TransferState, _logger
from src.transfers.abc import AbstractReader, AbstractSender
from src.transfers.mixins import *
from ._fileio import FileItemReader
from ._fileobject import FileItem


# nah, this is not a function definition
class Sender(
    ExceptionRouterMixIn,  # keep at the top of the mro, cause calls to these methods are more
    # probably called only once or twice
    ControlMixIn,
    CommonAExitMixIn,
    # probably called on rare occasion
    CancelOperationMixIn,
    AbstractSender,
):
    """Send a bunch of files

    Transfer layout::

        [{1} b'1'] -> [{2} file metadata] -> [{3} file contents] -(ok)-> [more ?] ->[{1}]
                                                      |               |
                                                  (exception)       [{4} b'0']
                                                      |                |
                                            [{5} preserve status]  [{7} finalize]
                                                      |
                                                [{6} pause]

    """

    version = const.VERSIONS["FO"]
    timeout = const.DEFAULT_TRANSFER_TIMEOUT

    def __init__(self, peer_obj, transfer_id, file_list, status_updater):
        self.transfer_task = None
        self.state = TransferState.PREPARING
        self.files_to_send = file_list
        self._transfer_id = transfer_id
        self.peer = peer_obj
        self.status_updater = status_updater
        self.should_stop = False
        self._current_file_idx = -1
        self.net_sender = None
        self.net_receiver = None
        self._expected_exps = set()
        self._on_completion_event = asyncio.Event()

    async def start_transfer(self):

        _logger.debug(f"{self._log_prefix} changing state to sending")
        self.state = TransferState.SENDING
        self.transfer_task = asyncio.current_task()

        while (
              self._current_file_idx < len(self.files_to_send) - 1
              and self.should_stop is False
        ):
            self._current_file_idx += 1
            await self.wrap_exp_handling(self.net_sender, HEADERS.CONTINUE_TRANSFER)

            await self.send_file_metadata(self.current_file)

            file_reader = FileItemReader(self.current_file)
            self.setup_status(file_reader)

            async with aclosing(self.send_one_file(file_reader)) as loop:
                try:
                    updater = self.status_updater.update_status  # localize function
                    _logger.info(f"sending file {self.current_file}")
                    async for _ in loop:
                        await updater(file_reader.seek_pos)
                        yield _
                finally:
                    self.current_file.seeked = file_reader.seek_pos
                    _logger.debug(
                        f"setting seeked attribute of {self.current_file=}, {file_reader=}"
                    )

            await self.status_updater.close()
            _logger.info(f"file sent {self.current_file}")

        # end of transfer, signalling that there are no more files
        await self.wrap_exp_handling(self.net_sender, HEADERS.END_OF_TRANSFER)
        _logger.debug(f"{self._log_prefix} sent final flag, waiting for ACK")
        assert (
              await self.wrap_exp_handling(self.net_receiver, 1)
              == HEADERS.END_OF_TRANSFER
        ), f"expecting ACK to be {HEADERS.END_OF_TRANSFER=}"

        _logger.info(
            f"{self._log_prefix} ACK received, completed sending, changing state to COMPLETED"
        )
        self.state = TransferState.COMPLETED
        self._on_completion_event.set()

    def setup_status(self, file_reader):
        return self.status_updater.status_setup(
            prefix=f"sending: {file_reader.file_item!s}",
            initial_limit=file_reader.seek_start_pos,
            final_limit=file_reader.seek_end_pos,
        )

    async def send_file_metadata(self, file_item):
        """
        Sends metadata for the given file to the remote peer.

        Encodes the file metadata into a binary packet and sends it.

        Args:
            file_item (FileItem): File whose metadata is being sent.
        """
        _logger.debug(
            f"sending file meta data {file_item.name=}, {file_item.seeked=}, {file_item.size=}"
        )
        file_object = bytes(file_item)
        file_packet = struct.pack("!I", len(file_object)) + file_object
        await self.wrap_exp_handling(self.net_sender, file_packet)

    async def send_one_file(self, file_reader: AbstractReader):
        """
        Transfers a single file using the given file reader.

        Args:
            file_reader (FileItemReader): File reader abstraction handling chunk reads.

        Yields:
            int: Number of bytes sent in the iteration. Used for async progress hooks.
        """
        try:
            async with file_reader.start_reading() as reading:
                async for chunk in reading:
                    yield await self.net_sender(chunk)
        except PermissionError as pe:
            _logger.warning(f"got {pe} for {file_reader=}, skipping that...")
        except Exception as exp:
            self.handle_exception(exp)

    async def resume_transfer(self):
        if not self.state == TransferState.PAUSED or self.should_stop is True:
            raise InvalidStateError(f"{self.state=}, {self.should_stop=}")

        _logger.debug(f"FILE[{self._transfer_id}] changing state to sending")
        self.state = TransferState.SENDING
        self._on_completion_event.clear()
        interrupted_file = self.files_to_send[self._current_file_idx]
        # synchronizing last file sent
        try:
            interrupted_file.seeked = await net.recv_int(
                self.net_receiver, net.LONG_INT
            )
        except ValueError as ve:
            self._raise_transfer_incomplete_and_change_state(ve)
        else:
            if interrupted_file.seeked != interrupted_file.size:
                self.status_updater.status_setup(
                    f"resuming file:{interrupted_file}",
                    interrupted_file.seeked,
                    interrupted_file.size,
                )
            else:
                # we got interrupted exactly when next file's file item is being sent
                self._current_file_idx += 1

        # continuing with remaining transfer
        async with aclosing(self.start_transfer()) as file_sender:
            async for items in file_sender:
                yield items

    def append_files(self, *file_items):
        if self.state in (TransferState.ABORTING, TransferState.COMPLETED):
            raise InvalidStateError(
                f"cannot append files when the transfer state={self.state}"
            )
        self.files_to_send.extend(file_items)

    def connection_made(self, connection):
        self.net_sender = connection.send
        self.net_receiver = connection.recv

    @property
    def id(self):
        return self._transfer_id

    @property
    def current_file(self):
        return self.files_to_send[self._current_file_idx]

    async def __aenter__(self):
        self.state = TransferState.CONNECTING
        return self

    @property
    def done(self):
        return self._on_completion_event
