import asyncio
import struct
from contextlib import aclosing
from pathlib import Path
from typing import override

import umsgpack

from src.avails import const, use
from src.avails.exceptions import TransferIncomplete
from src.avails.useables import recv_int
from src.transfers import TransferState
from src.transfers.files._fileobject import FileItem
from src.transfers.files.receiver import Receiver
from src.transfers.files.sender import Sender
from src.transfers.status import StatusMixIn

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


class DirSender(Sender):
    """
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
        self.dir_iterator = self.root_path.rglob('*')
        self._current_file = None

    async def send_files(self):
        self.send_files_task = asyncio.current_task()

        for item in self.dir_iterator:
            if self.to_stop:
                break

            if item.is_dir():
                await self.__send_code_parts(_PATH_CODE, item)
                self._current_file = FileItem(item, 0)
                continue

            if item.is_file():
                self._current_file = await self._send_file_item(item)
                if self.current_file.size > 0:
                    async with aclosing(self.send_one_file(self.current_file)) as sender:
                        async for i in sender:
                            yield i

                print("OK" if await self.recv_func(1) == _FILE_CODE else "NOT OK")

        await self.send_func(b'\x00')  # code to inform end of transfer

    @override
    async def _send_file_item(self, file_path):
        await self.__send_code_parts(_FILE_CODE, file_path)
        file_item = FileItem(file_path, 0)
        await self.send_func(struct.pack('!Q', file_item.size))
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
            await self.send_func(code)  # code to inform that there are more files to get
            await self.send_func(struct.pack('!I', len(dumped_code)) + dumped_code)
            print(f"code_len={len(dumped_code)}")

        except Exception as exp:
            self.handle_exception(exp)

        return parent, name

    def pause(self):
        pass

    def continue_transfer(self):
        pass

    async def cancel(self):
        pass

    @property
    def current_file(self):
        return self._current_file


class DirReceiver(Receiver):
    """
                                     ------------------------------------------------
                              (FILE) INT(4) | parents | name | FILE SIZE(8) | FILE_CONTENTS
                              |      -------------------------------------------------
                              |
        (1 byte) STOP or FILE
                              |
                              |
                              |      ----------------------
                              (PATH) INT(4) | parents | name
                                     ----------------------

    """

    def __init__(self, peer_obj, transfer_id, download_path, status_iter):
        super().__init__(peer_obj, transfer_id, download_path, status_iter)

    async def recv_files(self):
        self.state = TransferState.RECEIVING
        self.recv_files_task = asyncio.current_task()

        while True:
            if not (code := await self._should_proceed()):
                break

            if code == _FILE_CODE:
                async with aclosing(self._recv_file_once()) as loop:
                    print(self.current_file)  # debug
                    async for _ in loop:
                        yield _
                await self.send_func(code)

            elif code == _PATH_CODE:
                parent, item_name = await self._recv_parts()
                full_path = Path(self.download_path, parent, item_name)
                full_path.mkdir(parents=True)
                print("creating directory", use.shorten_path(full_path, 40))  # debug
                self._current_file = FileItem(full_path, 0)
                yield full_path, None

    @override
    async def _recv_file_item(self):
        parent, item_name = await self._recv_parts()
        try:
            size = await use.recv_int(self.recv_func, use.LONG_INT)
        except ValueError as ve:
            raise TransferIncomplete from ve
        file = FileItem(Path(self.download_path, parent, item_name), 0)
        file.size = size
        return file

    async def _recv_parts(self):
        try:
            code_len = await recv_int(self.recv_func)
            print(f"{code_len=}")
            parent, item_name = umsgpack.loads(await self.recv_func(code_len))
            if const.IS_WINDOWS:
                item_name = item_name.replace("\\", "_")
            return parent, item_name
        except (struct.error, umsgpack.UnpackException) as exp:
            raise TransferIncomplete("failed to receive item code") from exp

    def pause(self):
        self.state = TransferState.PAUSED
        self.send_func.pause()
        self.recv_func.pause()

    def resume(self):
        self.state = TransferState.RECEIVING
        self.send_func.resume()
        self.recv_func.resume()

    async def continue_transfer(self):
        self.state = TransferState.RECEIVING
