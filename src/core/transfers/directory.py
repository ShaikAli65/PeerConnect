import asyncio
import logging
import struct
from contextlib import aclosing
from pathlib import Path

import umsgpack

from src.avails import connect, const
from src.avails.exceptions import TransferIncomplete
from src.avails.status import StatusMixIn
from src.avails.useables import LONG_INT, recv_int
from src.core.transfers._fileobject import FileItem, TransferState, recv_file_contents, send_actual_file

_logger = logging.getLogger(__name__)

_FILE_CODE = b'\x00'
_PATH_CODE = b'\x01'


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


class Sender(StatusMixIn):
    timeout = 5

    def __init__(self, root_path, transfer_id, send_func, recv_func, yield_freq=10):
        """
        Args:
            root_path(Path): root path to read from and start the transfer
            transfer_id(str): transfer id that synchronized both sides
            send_func(connect.Sender): function to call upon to send file data when ready
            recv_func(connect.Receiver) : function to call upon to receive file data when ready
            yield_freq(int): status yield frequency
        """
        self.state = TransferState.PREPARING
        self.root_path = root_path
        self.current_file = None
        self.id = transfer_id
        self.send_bytes = send_func
        self.recv_bytes = recv_func
        self.proceed_flag = asyncio.Event()
        self.dir_iterator = self.root_path.rglob('*')
        self.current_dir_sending_state_info = None
        super().__init__(yield_freq)

    async def start(self):
        for item in self.dir_iterator:
            if self.proceed_flag.is_set():
                break
            await self.send_bytes(b'\x01')  # code to inform that there are more files to get

            await self._send_code(item)
            yield item
            if item.is_file():
                file_item = FileItem(path=item, seeked=0)

                await self.send_bytes(struct.pack('!Q', file_item.size))

                if file_item.size <= 0:
                    continue

                async with aclosing(
                        self._send_file(file_item)
                ) as sender:
                    async for i in sender:
                        yield i

        await self.send_bytes(b'\x00')  # code to inform end of transfer

    async def _send_file(self, file_item):

        self.status_setup(f"[DIR] sending : {file_item}", file_item.seeked, file_item.size)
        async with aclosing(
                send_actual_file(self.send_bytes, file_item)
        ) as file_sender:
            async for seeked in file_sender:
                self.update_status(seeked)
                if self.should_yield():
                    yield file_item, seeked

    async def _send_code(self, path: Path):
        code = None
        if path.is_dir():
            code = _PATH_CODE
        elif path.is_file():
            code = _FILE_CODE

        rel_path = path.relative_to(self.root_path)
        parent = rel_path.parent
        name = rel_path.name

        if const.IS_WINDOWS:
            parent = parent.as_posix()
        if const.IS_LINUX:
            name = name.replace('\\', '_')

        dumped_code = umsgpack.dumps((parent, name, code))
        await self.send_bytes(struct.pack('!I', len(dumped_code)))
        await self.send_bytes(dumped_code)
        return parent, name, code

    def stop(self):
        pass

    def pause(self):
        pass

    def continue_transfer(self):
        pass


class Receiver(StatusMixIn):
    def __init__(self, transfer_id, recv_func, send_func, download_path, status_yield_freq):
        self.id = transfer_id
        self.get_bytes = recv_func
        self.send_bytes = send_func
        self.stop_flag = asyncio.Event()
        self.download_path = download_path
        self.state = TransferState.PREPARING
        self.logger_prefix = f"DIR[{self.id}]"
        self._current_item = None
        super().__init__(status_yield_freq)

    async def start(self):
        self.state = TransferState.RECEIVING
        stopper = self.stop_flag.is_set
        while not stopper():
            what = await self.get_bytes(1)
            if what == b'\x00':  # no more files to get
                break

            parent, item_name, code = await self._recv_code()
            print('received code', (parent, item_name, code))  # debug
            full_path = Path(self.download_path, parent, item_name)

            if code == _FILE_CODE:
                file_item = await self._recv_file_item(full_path)
                async with aclosing(self._handle_file(file_item)) as f:
                    async for t in f:
                        yield t

            elif code == _PATH_CODE:
                full_path.mkdir(parents=True)
                print("creating directory", full_path)  # debug
                yield full_path, None

            # await self._echo_code(code)

    async def _recv_code(self):
        try:
            code_len = await recv_int(self.get_bytes)
            parent, item, code = umsgpack.loads(await self.get_bytes(code_len))
            return parent, item, code
        except (struct.error, umsgpack.UnpackException) as exp:
            self.state = TransferState.PAUSED
            _logger.error(f"{self.logger_prefix} failed to receive item code, changed state to {self.state}",
                          exc_info=True)
            raise TransferIncomplete("failed to receive item code") from exp

    async def _recv_file_item(self, file_path: Path):
        try:
            size = await recv_int(self.get_bytes, type=LONG_INT)
        except ValueError as ve:
            self.state = TransferState.PAUSED
            _logger.error(f"{self.logger_prefix} failed to receive file size, changed state to {self.state}",
                          exc_info=True)
            raise TransferIncomplete("failed to receive file size") from ve

        file_item = FileItem(file_path, 0)
        file_item.size = size
        return file_item

    async def _handle_file(self, file_item):

        if file_item.size <= 0:
            print("[DIR] empty file, creating", file_item)
            file_item.path.touch()
            return

        self.status_setup(f"[DIR] receiving file: {file_item}", file_item.seeked, file_item.size)

        receiver = recv_file_contents(self.get_bytes, file_item)
        try:
            async with aclosing(receiver) as receiver:
                async for received_size in receiver:
                    self.update_status(received_size)
                    if self.should_yield():
                        yield file_item, received_size

        except TransferIncomplete:
            self.state = TransferState.PAUSED
            self._reraise_error_and_log(f"file contents, {file_item}")

    async def _echo_code(self, code):
        try:
            await self.send_bytes(code)  # echo back code to confirm
        except OSError as oe:
            self.state = TransferState.PAUSED
            _logger.error(f"{self.logger_prefix} failed to send confirmation code, changed state to {self.state}")
            raise TransferIncomplete("failed to send confirmation code") from oe

    def pause(self):
        self.state = TransferState.PAUSED
        self.send_bytes.pause()
        self.get_bytes.pause()

    def resume(self):
        self.state = TransferState.RECEIVING
        self.send_bytes.resume()
        self.get_bytes.resume()

    async def continue_transfer(self):
        self.state = TransferState.RECEIVING
        self.stop_flag.clear()

        if self._current_item:
            await self.send_bytes(b'\x01')
            packed_seeked = struct.pack('!Q', self._current_item.seeked)
            await self.send_bytes(packed_seeked)
            # synchronizing file state

        await self.send_bytes(b'\x00')
        # resuming transfer
        async with aclosing(self.start()) as recv:
            async for status in recv:
                yield status

    def _reraise_error_and_log(self, msg):
        _logger.error(
            f"{self.logger_prefix} failed to receive {msg}, changed state to {self.state}",
            exc_info=True
        )
        raise

    async def stop(self):
        pass
