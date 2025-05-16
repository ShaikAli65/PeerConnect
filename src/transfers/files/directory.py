import asyncio
import struct
from contextlib import aclosing
from pathlib import Path
from typing import Generator

import umsgpack

from src import net
from src.avails import const, use
from src.avails.exceptions import TransferIncomplete
from src.avails.useables import override
from src.transfers import TransferState, _logger
from src.transfers.status import StatusMixIn
from . import async_open
from ._fileio import FileItemReader
from ._fileobject import FileItem
from .receiver import Receiver
from .sender import Sender

_FILE_CODE = b'\x01'
_PATH_CODE = b'\x02'


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
        _logger.error(f"The directory {abs_path} does not exist or is not a directory.")
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


class DirSender(Sender):
    """
    Data Layout:

                |  DIR -> INT(4) | PARENT | NAME | goto `code`
                |
    (1B) | code |
                |
                |  FILE -> INT(4) | PARENT | NAME | FILE_SIZE(8) | FILE CONTENTS | goto `code`
    """

    timeout = const.DEFAULT_TRANSFER_TIMEOUT

    def __init__(self, peer_obj, transfer_id, root_path, status_updater):
        """
        Args:
            root_path(Path): root path to read from and start the transfer
            transfer_id(str): transfer id that synchronized both sides
            status_updater(StatusMixIn): StatusMixIn object to update status of transfer
        """
        super().__init__(peer_obj, transfer_id, [], status_updater)
        self.root_path = root_path
        self.dir_iterator: Generator[Path, None, None] = self.root_path.rglob('*')
        self._current_file = None
        _logger.debug(f"{self._log_prefix} created new directory sender")

    @override
    async def start_transfer(self):
        self.transfer_task = asyncio.current_task()

        _logger.debug(f'{self._log_prefix} changing state to sending')
        self.state = TransferState.SENDING

        for item in self.dir_iterator:
            if self.should_stop:
                break

            if item.is_dir():
                _logger.debug(f"{self._log_prefix} sending sub-directory")
                await self.__send_code_parts(_PATH_CODE, item)
                self._current_file = FileItem(item, 0)
                continue

            if item.is_file():
                try:
                    async with async_open(item, 'rb'):
                        pass
                except PermissionError as pe:
                    _logger.debug(
                        f"{self._log_prefix} got permission error{pe!r}, skipping that file={item!s}")
                    continue

                self._current_file = await self.send_file_metadata(item)
                _logger.debug(f"{self._log_prefix} sent file metadata={item!s}")
                if self._current_file.size <= 0:
                    assert (await self.net_receiver(1)) == _FILE_CODE
                    continue
                f_reader = FileItemReader(self._current_file)
                self.setup_status(f_reader)
                async with aclosing(self.send_one_file(f_reader)) as sender:
                    updater = self.status_updater.update_status  # localize function
                    _logger.debug(f"{self._log_prefix} sending file data={item!s}")
                    async for i in sender:
                        await updater(f_reader.seek_pos)
                        yield i

                _logger.debug(f"{self._log_prefix} sent file data={item!s}")
                assert (await self.net_receiver(1)) == _FILE_CODE

        _logger.debug(f"{self._log_prefix} sending end of transfer code")
        await self.net_sender(b'\x00')  # code to inform end of transfer
        self.state = TransferState.COMPLETED

    @use.override
    async def send_file_metadata(self, file_path):
        await self.__send_code_parts(_FILE_CODE, file_path)
        file_item = FileItem(file_path, 0)
        await self.wrap_exp_handling(self.net_sender, struct.pack('!Q', file_item.size))
        return file_item

    async def __send_code_parts(self, code, path: Path):

        rel_path = path.relative_to(self.root_path)
        parent = rel_path.parent
        name = rel_path.name

        if const.IS_WINDOWS:
            parent = parent.as_posix()
        if const.IS_LINUX:
            name = name.replace('\\', '_')

        dumped_code = umsgpack.dumps((parent, name))
        try:
            await self.net_sender(code)  # code to inform that there are more files to get
            await self.net_sender(struct.pack('!I', len(dumped_code)) + dumped_code)
            _logger.debug(f"{self._log_prefix} sent code parts")

        except Exception as exp:
            _logger.debug(f"{self._log_prefix} exception when sending code parts", exc_info=exp)
            self.handle_exception(exp)

        return parent, name

    def resume_transfer(self):
        raise NotImplementedError

    @property
    def current_file(self) -> FileItem:
        return self._current_file


class DirReceiver(Receiver):
    """
    Data Layout::

                                     -------------------------------------------------------
                              (FILE) INT(4) | parents | name | FILE SIZE(8) | FILE_CONTENTS
                              |      -------------------------------------------------------
                              |
        (1 byte) STOP or FILE
                              |
                              |
                              |      ------------------------
                              (PATH) INT(4) | parents | name
                                     ------------------------

    """

    async def start_transfer(self):
        _logger.debug(f"{self._log_prefix} changing state to CONNECTING")
        self.state = TransferState.CONNECTING
        await self.connection_wait

        _logger.debug(f"{self._log_prefix} changing state to RECEIVING")
        self.state = TransferState.RECEIVING

        self.transfer_task = asyncio.current_task()
        _logger.debug(f"{self._log_prefix} receiving directory, into {self.download_path}")

        while True:
            if not (code := await self._should_proceed()):
                _logger.debug(f"{self._log_prefix} got exit code, finalizing recv loop")
                break

            if code == _FILE_CODE:
                _logger.debug(f"{self._log_prefix} got sub-file code")
                async with aclosing(self._recv_file_once()) as loop:
                    _logger.debug(f"receiving sub-file={self.current_file}")
                    async for _ in loop:
                        yield _
                await self.net_sender(code)

            elif code == _PATH_CODE:
                _logger.debug(f"{self._log_prefix} got sub-directory code")
                parent, item_name = await self._recv_parts()
                full_path = Path(self.download_path, parent, item_name)
                _logger.debug(
                    f"creating directory at {full_path}, ({self.download_path=},{parent=},{item_name=})")
                full_path.mkdir(parents=True)
                self._current_file = FileItem(full_path, 0)
                yield full_path, None

        self.state = TransferState.COMPLETED

    @use.override
    async def _recv_file_item(self):
        parent, item_name = await self._recv_parts()
        try:
            size = await net.recv_int(self.net_receiver, net.LONG_INT)
        except ValueError as ve:
            raise TransferIncomplete from ve
        file = FileItem(Path(self.download_path, parent, item_name), 0)
        file.size = size
        return file

    async def _recv_parts(self):
        try:
            code_len = await net.recv_int(self.net_receiver)
            parent, item_name = umsgpack.loads(await self.net_receiver(code_len))
            if const.IS_WINDOWS:
                item_name = item_name.replace("\\", "_")
            return parent, item_name
        except (struct.error, umsgpack.UnpackException) as exp:
            raise TransferIncomplete("failed to receive item code") from exp

    async def resume_transfer(self):
        return NotImplemented
