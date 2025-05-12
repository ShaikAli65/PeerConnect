"""IOReader and IOWriter wrappers for `FileItem`

Notes:
    These classes are made specifically to use withing `transfers` package,
    i.e. these are not for general purpose use
"""

import asyncio
import functools
import mmap
import os
from abc import ABC
from contextlib import asynccontextmanager
from io import BytesIO, TextIOWrapper
from typing import AsyncGenerator, BinaryIO

from src.avails.exceptions import InvalidStateError
from src.transfers import thread_pool_for_disk_io as _th_pool
from src.transfers.abc import AbstractRWBase, AbstractReader, AbstractWriter
from ._fileobject import FileItem, calculate_chunk_size

USE_MMAP_READ = True

__all__ = (
    "FileItemReader",
    "FileItemWriter",
    "async_open",
)


@asynccontextmanager
async def async_open(*args):
    loop = asyncio.get_running_loop()
    fd: TextIOWrapper | BinaryIO = await loop.run_in_executor(_th_pool, open, *args)  # noqa
    async with fd:
        yield fd


class FileItemRWBase(AbstractRWBase, ABC):
    """Adds start and stop index, defaults to seeked and size attributes of FileItem instance passed in
    """
    __slots__ = (
        "file_item",
        "_start_index",
        "_stop_index",
    )

    def __init__(self, file: FileItem):
        self.file_item = file
        self._start_index = None
        self._stop_index = None
        self.set_bounds(file.seeked, file.size)

    @property
    def seek_end_pos(self):
        return self._stop_index

    @property
    def seek_start_pos(self):
        return self._start_index

    @property
    def size(self):
        return self._stop_index - self._start_index

    async def set_bounds(self, start, end):
        """Set the boundaries, this may be invalid if the reader/writer is already started"""
        assert end >= start, f"{end=} should be greater that {start=}"
        self._start_index = start
        self._stop_index = end

    def __repr__(self):
        return f"<{self.__class__.__name__}({self.file_item!r}, bounds={(self._start_index, self._stop_index)})>"


class FileItemReader(FileItemRWBase, AbstractReader):
    __slots__ = "fd", "_chunk_len", "_reader_gen"

    def __init__(self, file: FileItem, chunk_size=None):
        """
        Opens file in **rb** mode from the ``path`` attribute from ``file item``
        reads ``seeked`` attribute of ``file item``
        if chunk_size parameter is not provided then calculates chunk size by calling ``calculate_chunk_size``

        Args:
            file(FileItem): file to read
            chunk_size(int): length of each chunk passed into ``send_function`` for each call
        """

        super().__init__(file)
        self.fd: BytesIO | None = None
        self._chunk_len = chunk_size or calculate_chunk_size(file.size)
        self._reader_gen: AsyncGenerator | None = None

    @asynccontextmanager
    async def start_reading(self):
        async with async_open(self.file_item.path, 'r+b') as fd:
            self.fd = fd
            if USE_MMAP_READ:
                self._reader_gen = self._mmap_reader()
            else:
                self._reader_gen = self._reader()

            try:
                yield self._reader_gen
            finally:
                await self.close()

    async def set_bounds(self, start, end):
        assert self._reader_gen.ag_running is False, "cannot set boundaries after start_reading called"
        self._start_index = start
        self._stop_index = end

    async def _mmap_reader(self):
        chunk_size = self._chunk_len
        seek = self._start_index

        with mmap.mmap(self.fd.fileno(), 0, access=mmap.ACCESS_READ) as f_mapped:
            asyncify = functools.partial(
                asyncio.get_running_loop().run_in_executor,
                _th_pool,
                f_mapped.__getitem__
            )

            for offset in range(seek, self._stop_index, chunk_size):
                chunk = await asyncify(slice(offset, offset + chunk_size))
                seek += len(chunk)
                yield chunk

    async def _reader(self):
        async_read = functools.partial(
            asyncio.get_running_loop().run_in_executor,
            _th_pool,
            self.fd.read
        )

        self.fd.seek(self._start_index)

        size = self._stop_index
        chunk = self._chunk_len
        while size > 0:
            chunk = await async_read(min(chunk, size))  # noqa
            size -= chunk
            yield chunk

    @property
    def seek_pos(self):
        return self.fd.tell() - self._start_index

    @property
    def reader(self):
        """Generator object that can be iterated over to get file contents"""
        return self._reader_gen

    async def close(self, *args):
        if self._reader_gen.ag_running is False:
            raise InvalidStateError("Not Started")

        await self._reader_gen.aclose()


class FileItemWriter(FileItemRWBase, AbstractWriter):
    __slots__ = "fd", "_fd_writer", "started"

    def __init__(self, file: FileItem):
        super().__init__(file)
        self.fd: BytesIO | None = None
        self._file_writer = None
        self.started = False

    @asynccontextmanager
    async def start_writing(self):
        """Initializes the file writing

        File opens in binary mode

        Usage::

            file_writer = FWriter(file_item)
            async with file_writer.start_writing() as f_writer:
                f_writer(data)

            # or
            async with file_writer.start_writing():
                file_writer.write(data)

        Returns:
             Callable[[bytes], Awaitable[int]] : async callable used to write data to file

        """
        async with self._setup_file():
            self.started = True
            # directly set file_writer as write method, `write` method just relaying the call
            setattr(self, 'write', self._file_writer)
            yield self._file_writer

    async def write(self, data: bytes):
        return await self._file_writer(data)

    @asynccontextmanager
    async def _setup_file(self):
        mode = (
            "xb" if self._start_index == 0 else "rb+"
        )  # Create a new file or open for reading and writing
        # Check for the existence of the file for resuming
        # A reason for going with more specific modes like xb or rb+ rather than using "w" modes
        # by any chance if the file_item is misconfigured and the file held by file_item is important
        # all the contents are cleared

        if self._start_index > 0 and not os.path.exists(self.file_item.path):
            print(f"File {self.file_item.path} not found for resuming transfer.")  # debug
            raise FileNotFoundError(
                f"File {self.file_item.path} not found for resuming transfer."
            )

        async with async_open(self.file_item.path, mode) as fd:
            self.fd = fd
            fd.seek(self._start_index)
            loop = asyncio.get_running_loop()
            self._file_writer = functools.partial(loop.run_in_executor, _th_pool, fd.write)
            yield

    @property
    def seek_pos(self):
        return self.fd.tell()

    async def close(self, *args):
        return self.fd.close()
