import asyncio
import contextlib
import enum
import mmap
import multiprocessing
import os
import struct
from pathlib import Path
from typing import Awaitable, Callable, Iterable

import tqdm
import umsgpack

from src.avails import const
from src.avails.exceptions import TransferIncomplete


def stringify_size(size):
    sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    index = 0
    while size >= 1024 and index < len(sizes) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {sizes[index]}"


def shorten_path(path, max_length):
    if len(path) <= max_length:
        return path
    parts = path.split(os.sep)
    if len(parts) <= 2:
        return path
    short_path = f"{parts[0]}{os.sep}...{os.sep}{parts[-1]}"
    for i in range(1, len(parts) - 1):
        short_path = f"{os.sep.join(parts[:i + 1])}{os.sep}...{os.sep}{os.sep.join(parts[-1 - i:])}"
        if len(short_path) <= max_length:
            return short_path
    return f"{short_path[:max_length - 3]}..."


class FileItem:
    """Designed to represent a file with its metadata

    Such as name, size, path, and whether it has been seeked.
    It provides methods to manage file renaming, error handling, and serialization.

    Attributes:
        __slots__: Used for memory optimization, defining the attributes the class can have.
        _name: The name of the file.
        size: The size of the file in bytes.
        path: The Path object representing the file's path.
        seeked: A variable indicating how much of the file has been read or processed.
        original_ext: Preserves the original file extension for potential renaming.

    Note:
        The add_error_ext method renames the file to include an error extension, while remove_error_ext restores the original name.
        Both methods handle edge cases, such as ensuring the original extension exists before attempting to restore it.

    """
    __slots__ = '_name', 'size', 'path', 'seeked', 'original_ext'

    def __init__(self, path, seeked):
        """Initializes the file object, fetching its size and name from the filesystem.

        Args:
            path(Path): file path to use operate with during transfer
            seeked(int): used to persist transfer state
        """
        self.path: Path = path
        self.seeked = seeked
        if self.path.exists():
            self.size = self.path.stat().st_size
        self._name = self.path.name

    def __str__(self):
        size_str = stringify_size(self.size)
        name_str = f"...{self._name[-20:]}" if len(self._name) > 20 else self._name
        str_str = f"FileItem({name_str}, {size_str}, {shorten_path(os.path.split(self.path)[0], 20)})"
        return str_str

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        self.path = self.path.with_name(self._name)

    @staticmethod
    def load_from(data: bytes, file_parent_path):
        name, size, seeked = umsgpack.loads(data)
        file = FileItem(Path(file_parent_path, name), seeked)
        file._name = name
        file.size = size
        return file

    def __bytes__(self):
        return umsgpack.dumps(tuple(self))

    def __iter__(self):
        return iter((self.name, self.size, self.seeked))

    def __repr__(self):
        return f"FileItem(name={self.name[:10]}, size={self.size}, seeked={self.seeked})"

    def add_error_ext(self, error_ext):
        """
        Adds error extension to file path and renames it
        original extension is preserved for undoing this operation
        Example:
            before:
                file_path = "a/b/c/d.txt"
                :param error_ext: = .error
            after:
                file_path = "a/b/c/d.txt.error"
        """
        self.original_ext = self.path.suffix
        new_path = self.path.with_suffix(error_ext)
        self.path.rename(new_path)
        self._name = self.path.name

    def remove_error_ext(self):
        """
        Removes the error extension from the file name,
        restoring it to its original name, renames the file path.

        If the original extension is not available, raises a ValueError.
        """
        if not hasattr(self, 'original_ext'):
            raise ValueError("Original extension is not set; cannot remove_and_close error extension.")

        # Restore the original name by replacing the current suffix with the original suffix
        original_path = self.path.with_suffix(self.original_ext)

        # Rename the file back to its original name
        if original_path.exists():
            raise FileExistsError(f"The original file {original_path} already exists.")

        self.path.rename(original_path)
        self._name = original_path.name  # Update the name attribute

    def __getitem__(self, item):
        return (self.name, self.size, self.path)[item]


class StatusCodes(enum.Enum):
    PAUSED = 5
    ABORTING = 6
    COMPLETED = 7


class PeerFilePool:
    retries = 8
    chunk_size = 1024 * 512,

    __slots__ = 'file_items', 'to_stop', '__error_ext', 'id', 'current_file', 'file_count', 'download_path'

    def __init__(
            self,
            file_items: list[FileItem] = None,
            *,
            _id,
            error_ext=const.FILE_ERROR_EXT,
            download_path=Path('.')
    ):
        self.__error_ext = error_ext
        self.file_items: list[FileItem] = list(file_items or [])
        self.to_stop = False
        self.id = _id

        # list index pointing to file that is currently getting processed
        # this keeps a reference to file item when receiving file
        self.current_file: FileItem | int = 0
        self.file_count = len(self.file_items)
        self.download_path = download_path

    async def send_files(self, send_function: Callable[[bytes], Awaitable[bool]]):
        # await self.__send_int(self.file_count, send_function)
        return await self.send_file_loop(self.current_file, send_function)

    async def send_file_loop(self, current_index, send_function):

        for index in range(current_index, len(self.file_items)):
            # there is another file incoming
            await send_function(struct.pack('?', True))
            file_item = self.file_items[index]
            self.current_file = index

            progress = await send_file_setup(send_function, file=file_item)
            result = await send_actual_file(send_function, file_item, progress)

            print("file sent", file_item)

            if (self.to_stop or result) is False:
                if self.to_stop:
                    with contextlib.suppress(OSError):
                        await send_function(struct.pack('?', False))
                        # we do nothing here because we are finalizing anyhow

                return False
            # self.current_file = self.file_items[index + 1]

        # end of transfer, signalling that there are no more files
        await send_function(struct.pack('?', False))

        return True

    async def receive_file_loop(self, recv_function):
        while True:
            try:
                what = struct.unpack('?', await recv_function(1))[0]
            except struct.error as e:
                if e.args == ("unpack requires a buffer of 1 bytes",):
                    raise TransferIncomplete(TransferState.PAUSED) from e
                raise

            if not what:
                print("received end of transfer signal, finalizing file recv loop")  # debug
                return TransferState.COMPLETED

            if self.to_stop:
                return TransferState.PAUSED

            file_item, progress = await recv_file_setup(recv_function, self.download_path)
            self.current_file = file_item
            self.file_items.append(file_item)
            try:
                await recv_actual_file(lambda: self.to_stop, recv_function, file_item, progress)
                print("completed receiving", self.current_file)  # debug
                self.file_count += 1
            except TransferIncomplete:
                # if ti.__cause__ and isinstance(ti.__cause__, OSError):
                #     if 'No space left on device' in str(ti.__cause__):
                #         add_error_ext(file_item, self.download_path, self.__error_ext)
                add_error_ext(file_item, self.download_path,
                              self.__error_ext)  # Mark error if not all data was received
                progress.close()
                raise
                # return False
            progress.close()

    async def send_files_again(self, receiver_sock):
        # ----------------------
        start_file = self.file_items[self.current_file]
        start_file.seeked = struct.unpack('!Q', await receiver_sock.recv(8))[0]
        progress = tqdm.tqdm(
            range(start_file.size),
            f"[PID:{multiprocessing.current_process().ident}]sending {start_file.name[:20]}... ",
            unit="B",
            unit_scale=True,
            unit_divisor=1024
        )
        await send_actual_file(receiver_sock.asendall, start_file, progress)
        progress.close()
        # -> ---------------------- file continuation part
        self.current_file += 1
        return await self.send_file_loop(self.current_file, receiver_sock)

    async def receive_files_again(self, sender_sock):
        # -> ----------------------
        start_file = self.current_file
        await sender_sock.asendall(start_file.seeked)
        progress = tqdm.tqdm(
            range(start_file.size),
            f"::receiving {start_file.name[:20]}... ",
            unit="B",
            unit_scale=True,
            unit_divisor=1024
        )
        what = await recv_actual_file(lambda: self.to_stop, sender_sock, start_file, progress)
        if not what:
            print('got error again returning')  # debug
            progress.close()
            return
        remove_error_ext(start_file, self.download_path)
        # -> ---------------------- file continuation part

        return await self.receive_file_loop(sender_sock.asendall)

    def attach_files(self, files: Iterable[FileItem]):
        self.file_items.extend(files)

    @staticmethod
    async def __get_int_from_sender(recv_function: Callable[[int], Awaitable[bytes]]):
        raw_int = await recv_function(4)
        return struct.unpack('!I', raw_int)[0]

    @staticmethod
    async def __send_int(integer, send_function: Callable[[bytes], Awaitable[bool]]):
        packed_int = struct.pack('!I', integer)
        return await send_function(packed_int)

    def __repr__(self):
        """
            Returns the file details
        """
        return f"<PeerFilePool(id={self.id}, paths={self.file_items!r})>"

    def __iter__(self):
        """
        Returns:
             Internal file_paths iterator
        """
        return self.file_items.__iter__()


def add_error_ext(file_item: FileItem, root_path, error_ext):
    """
        Handles file error by renaming the file with an error extension.

        Arguments:
            file_item(FileItem): file item to operate on
            root_path(Path): directory to validate new name with
            error_ext(str): dotted extension to add to file item
    """
    try:
        file_item.add_error_ext(error_ext)
    except FileExistsError:
        return validatename(file_item, root_path)


def remove_error_ext(file_item, root_path):
    """
        Removes file error ext by renaming the file with its actual file extension.

        Note:
            the parameter ``file_item`` should have gone through add_error_ext function call which
            preserves the actual extension

        Args:
            file_item(FileItem): file item to operate on
            root_path(Path): directory to validate new name with
    """
    try:
        file_item.remove_error_ext()
    except FileExistsError:
        return validatename(file_item, root_path)


def validatename(file_item: FileItem, root_path) -> str:
    """
    Ensures a unique filename if a file with the same name already exists
    in the `self.download_dir`

    Args:
        file_item (FileItem): The original filename.
        root_path(Path): Directory path to validate with
    Returns:
        str: The validated filename, ensuring uniqueness.
    """

    original_path = Path(file_item.path)
    base = original_path.stem  # Base name without extension
    ext = original_path.suffix  # File extension
    new_file_name = original_path.name  # Start with the original name

    counter = 1
    while (root_path / new_file_name).exists():
        new_file_name = f"{base} ({counter}){ext}"
        counter += 1
    file_item.name = new_file_name

    return new_file_name


def calculate_chunk_size(file_size: int):
    min_buffer_size = 64 * 1024  # 64 KB
    max_buffer_size = (2 ** 20) * 2  # 2 MB

    min_file_size = 2 ** 10
    max_file_size = (2 ** 30) * 10  # 10 GB

    if file_size <= min_file_size:
        return min_buffer_size
    elif file_size >= max_file_size:
        return max_buffer_size
    else:
        # Linear scaling between min and max buffer sizes
        buffer_size = min_buffer_size + (max_buffer_size - min_buffer_size) * (file_size - min_file_size) / (
                max_file_size - min_file_size)
    return int(buffer_size)


async def send_file_setup(send_function, file: FileItem):
    print("sending file data", f"[PID:{os.getpid()}]")  # debug

    file_object = bytes(file)
    file_packet = struct.pack('!I', len(file_object)) + file_object
    await send_function(file_packet)  # possible : any sort of socket/connection errors

    send_progress = tqdm.tqdm(
        range(file.size),
        f"[PID:{multiprocessing.current_process().ident}]"
        f" sending {file.name[:17] + '...' if len(file.name) > 20 else file.name} ",
        unit="B",
        unit_scale=True,
        unit_divisor=1024
    )
    return send_progress


async def send_actual_file(send_function, file: FileItem, send_progress, chunk_len=None, timeout=4):
    """Sends file to other send using `send_function`

    calls ``send_function`` and awaits on it every time this function tries to send a chunk

    Note:
        file parameter gets mutated and it's size attribute gets updated according to data sent

    Arguments:
        send_function(Callable): function to call when a chunk is ready
        file(FileItem): file to send
        send_progress(tqdm.tqdm): tqdm progress to update accordingly
        chunk_len(int): length of each chunk passed into ``send_function`` for each call
        timeout(int): timeout in seconds used to wait upon send_function

    Returns:
        bool: True if file transfer was successful
    """
    send_progress.update(file.seeked)
    chunk_size = chunk_len or calculate_chunk_size(file.size)
    print('sending file data', file)  # debug
    with open(file.path, 'rb') as f:
        seek = file.seeked
        f_mapped = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        for offset in range(seek, file.size, chunk_size):
            chunk = f_mapped[offset: offset + chunk_size]
            try:
                await asyncio.wait_for(send_function(chunk), timeout)
                # :todo: add timeout mechanisms
            except ConnectionResetError:
                file.seeked = seek  # can be ignored mostly for now
                raise
            send_progress.update(len(chunk))
            seek += len(chunk)
            # await asyncio.sleep(0)
    file.seeked = seek  # can be ignored mostly for now
    return True


async def recv_file_setup(recv_function, download_path):
    raw_int = await recv_function(4)
    file_item_size = struct.unpack('!I', raw_int)[0]
    raw_file_item = await recv_function(file_item_size)
    file_item = FileItem.load_from(raw_file_item, download_path)
    validatename(file_item, download_path)
    progress = tqdm.tqdm(
        range(file_item.size),
        f"::receiving {file_item.name[:17] + '...' if len(file_item.name) > 20 else file_item.name} ",
        unit="B",
        unit_scale=True,
        unit_divisor=1024
    )
    return file_item, progress


async def recv_actual_file(stopping_flag, recv_function, file_item: FileItem, progress):
    """
    Receive a file over a network connection and write it to disk.

    Args:
        recv_function (Asynchronous Callable): A function to receive data.
        file_item (FileItem): An object containing file metadata.
        progress (ProgressTracker): An object to track progress of file writing.
        stopping_flag(Callable): gets called to check when looping over byte chunks received from ``recv_function``
    Returns:
        bool: True if the file was received successfully, False otherwise.
    """

    mode = 'xb' if file_item.seeked == 0 else 'rb+'  # Create a new file or open for reading and writing
    # Check for the existence of the file for resuming
    if file_item.seeked > 0 and not os.path.exists(file_item.path):
        print(f"File {file_item.path} not found for resuming transfer.")  # debug
        raise FileNotFoundError(f"File {file_item.path} not found for resuming transfer.")

    chunk_size = calculate_chunk_size(file_item.size)
    any_exception = None
    try:
        with open(file_item.path, mode) as file:
            f_write, remaining_bytes = file.write, file_item.size
            file.seek(file_item.seeked)
            remaining_bytes -= file_item.seeked
            progress.update(file_item.seeked)

            while (not stopping_flag()) and remaining_bytes > 0:
                data = await recv_function(min(chunk_size, remaining_bytes))
                if not data:
                    break

                f_write(data)  # Attempt to write data to file
                # :TODO deal with blocking nature of file i/o

                remaining_bytes -= len(data)
                progress.update(len(data))
    except Exception as e:
        any_exception = e
    finally:
        file_item.seeked = file_item.size - remaining_bytes  # Update the seek position
        if remaining_bytes > 0:
            incomplete_transfer = TransferIncomplete(remaining_bytes)
            if any_exception:
                raise incomplete_transfer from any_exception
            else:
                raise incomplete_transfer


"""
1. FileItem Class (_FileItem)

2. PeerFilePool Class

    Overview:
        The PeerFilePool class manages a collection of _FileItem objects and is responsible for sending and receiving 
        files over a network. It uses asynchronous functions to handle file transfer efficiently.

    Key Attributes:
        file_items: A set of _FileItem objects representing the files to be transferred.
        to_stop: A boolean flag indicating if the file transfer should be stopped.
        id: An identifier for the peer file pool instance.
        current_file: An iterator or a single _FileItem instance representing the file currently being processed.
        download_path: The path where files will be downloaded or saved.

    Key Methods:
    send_files: Initiates the sending process and sends the number of files to the receiver.
    send_file_loop and send_file_setup: Handle the actual sending of files, using tqdm for progress indication.
    recv_files: Receives files from a sender, initializing the process by receiving the file count.
    recv_actual_file: Manages the actual receiving of the file data and handles errors.
    _add_error_ext and _remove_error_ext: These are utility methods for handling file errors during transmission.

    Error Handling:
        recv_actual_file: Contains logic to check for existing files and handle errors like running out of disk space. If an error occurs during writing, it marks the file with an error extension.
        The send_actual_file method incorporates error handling for connection issues, ensuring that the transfer can resume if interrupted.

3. Utility Functions:
    stringify_size: Converts file sizes from bytes to a human-readable format.
    shorten_path: Shortens file paths for display, making them more manageable in log messages.
    calculate_chunk_size: Determines the optimal chunk size for reading/writing files based on their size, balancing memory efficiency and performance.

4. Analysis of Logic
    Overall Flow:
    File Initialization: When a _FileItem is created, it fetches file properties (size and name) from the disk.
    Sending Files: PeerFilePool sends a list of _FileItem objects, reporting progress and handling errors as they arise.
    Receiving Files: Files are received asynchronously, with checks for existing files to avoid overwriting and renaming on error.
    Error Management: When a file transfer fails (e.g., due to lack of space), the system renames the file to indicate the issue. Upon successful transfer, it restores the file to its original state.
"""


class TransferState(enum.Enum):
    #
    # remember to reflect changes in `StatusCodes` in fileobject.py
    #
    PREPARING = 1
    CONNECTING = 2
    SENDING = 3
    RECEIVING = 4
    PAUSED = 5
    ABORTING = 6
    COMPLETED = 7
