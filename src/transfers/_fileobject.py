import asyncio
import enum
import mmap
import os
from asyncio import CancelledError
from contextlib import contextmanager
from pathlib import Path

import umsgpack

from src.avails import use
from src.avails.exceptions import TransferIncomplete


def stringify_size(size):
    sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    index = 0
    while size >= 1024 and index < len(sizes) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {sizes[index]}"


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

    def __str__(self):
        size_str = stringify_size(self.size)
        name_str = f"...{self._name[-20:]}" if len(self._name) > 20 else self._name
        str_str = f"FileItem({name_str}, {size_str}, {use.shorten_path(self.path, 20)})"
        return str_str

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
    in the `root_path`

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


def calculate_chunk_size(
        file_size: int,
        *,
        min_size=64 * 1024,  # 64 KB
        max_size=(2 ** 20) * 2,  # 2 MB
):
    min_file_size = 2 ** 10
    max_file_size = (2 ** 30) * 10  # 10 GB

    if file_size <= min_file_size:
        return min_size
    elif file_size >= max_file_size:
        return max_size
    else:
        # Linear scaling between min and max buffer sizes
        buffer_size = min_size + (max_size - min_size) * (file_size - min_file_size) / (
                max_file_size - min_file_size)

    return int(buffer_size - (buffer_size % 1024))


async def send_actual_file(
        send_function,
        file,
        *,
        chunk_len=None,
        timeout=5
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

    Yields:
        number indicating the sent file size
    """

    chunk_size = chunk_len or calculate_chunk_size(file.size)

    with open(file.path, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as f_mapped:
            seek = file.seeked
            for offset in range(seek, file.size, chunk_size):
                chunk = f_mapped[offset: offset + chunk_size]
                await asyncio.wait_for(send_function(chunk), timeout)
                seek += len(chunk)
                file.seeked = seek
                yield seek


async def recv_file_contents(recv_function, file_item, *, chunk_size=None):
    """Receive a file over a network connection and write it to disk.

    if ``FileItem.seeked`` attribute is non zero then the file at ``file_item.path`` is checked for existence
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

    with _setup_transfer(chunk_size, file_item) as t:
        chunk_size, file_size, f_writer, remaining_bytes = t

        while remaining_bytes > 0:
            data = await recv_function(min(chunk_size, remaining_bytes))
            if not data:
                break

            f_writer(data)  # Attempt to write data to file

            remaining_bytes -= len(data)
            file_item.seeked += len(data)
            # :TODO deal with blocking nature of file i/o
            yield file_size - remaining_bytes


@contextmanager
def _setup_transfer(chunk_size, file_item):
    mode = 'xb' if file_item.seeked == 0 else 'rb+'  # Create a new file or open for reading and writing
    # Check for the existence of the file for resuming

    if file_item.seeked > 0 and not os.path.exists(file_item.path):
        print(f"File {file_item.path} not found for resuming transfer.")  # debug
        raise FileNotFoundError(f"File {file_item.path} not found for resuming transfer.")

    chunk_size = chunk_size or calculate_chunk_size(file_item.size)
    remaining_bytes = file_item.size
    with open(file_item.path, mode) as fd:
        fd.seek(file_item.seeked)
        remaining_bytes -= file_item.seeked
        try:
            yield chunk_size, file_item.size, fd.write, remaining_bytes
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


class TransferState(enum.Enum):
    PREPARING = 1
    CONNECTING = 2
    SENDING = 3
    RECEIVING = 4
    PAUSED = 5
    ABORTING = 6
    COMPLETED = 7
