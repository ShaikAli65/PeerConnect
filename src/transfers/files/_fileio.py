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
from src.transfers import _logger, thread_pool_for_disk_io as _th_pool
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
    with fd:
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

    def set_bounds(self, start, end):
        """Set the boundaries, this may be invalid if the reader/writer is already started"""
        assert end >= start, f"{end=} should be greater that {start=}"
        self._start_index = start
        self._stop_index = end

    def __repr__(self):
        return (f"<{self.__class__.__name__}("
                f"{self.file_item!r}, "
                f"bounds={(self._start_index, self._stop_index)}, "
                f"curr={self.seek_pos}"
                f")>")


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

        self.fd: BytesIO | None = None
        self._chunk_len = chunk_size or calculate_chunk_size(file.size)
        self._reader_gen: AsyncGenerator | None = None
        super().__init__(file)
        self._seek = self._start_index

    @asynccontextmanager
    async def start_reading(self):
        async with async_open(self.file_item.path, 'rb') as fd:
            self.fd = fd
            if USE_MMAP_READ:
                try:
                    self._reader_gen = self._mmap_reader()
                except PermissionError:
                    self._reader_gen = self._reader()
            else:
                self._reader_gen = self._reader()

            try:
                yield self._reader_gen
            finally:
                await self.close()

    def set_bounds(self, start, end):

        if self._reader_gen and self._reader_gen.ag_running is True:
            raise InvalidStateError("cannot set boundaries after start_reading called")

        self._start_index = start
        self._seek = start
        self._stop_index = end

    async def _mmap_reader(self):
        chunk_size = self._chunk_len

        with mmap.mmap(self.fd.fileno(), 0, access=mmap.ACCESS_READ) as f_mapped:
            asyncify = functools.partial(
                asyncio.get_running_loop().run_in_executor,
                _th_pool,
                f_mapped.__getitem__
            )

            total = self._stop_index - self._start_index
            full_chunks = total // chunk_size
            remainder = total % chunk_size

            base = self._start_index
            for i in range(full_chunks):
                start = base + i * chunk_size
                stop = start + chunk_size
                chunk = await asyncify(slice(start, stop))
                self._seek += len(chunk)
                yield chunk

            if remainder:
                start = base + full_chunks * chunk_size
                stop = self._stop_index
                chunk = await asyncify(slice(start, stop))
                self._seek += len(chunk)
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
            size -= len(chunk)
            self._seek += len(chunk)
            yield memoryview(chunk)

    @property
    def seek_pos(self):
        return self._seek

    @property
    def reader(self):
        """Generator object that can be iterated over to get file contents"""
        return self._reader_gen

    async def close(self, *args):
        return await self._reader_gen.aclose()


class FileItemWriter(FileItemRWBase, AbstractWriter):
    __slots__ = "fd", "_fd_writer", "started"

    def __init__(self, file: FileItem):
        self.fd: BytesIO | None = None
        self._file_writer = None
        self.started = False
        self._seek = 0
        super().__init__(file)

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
            yield self._file_writer

    async def write(self, data: bytes):
        w = await self._file_writer(data)
        self._seek += w
        return w

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
            _logger.info(f"File {self.file_item.path} not found for resuming transfer.")  # debug
            raise FileNotFoundError(
                f"File {self.file_item.path} not found for resuming transfer."
            )

        async with async_open(self.file_item.path, mode) as fd:
            self.fd = fd
            self._seek += self._start_index

            fd.seek(self._start_index)
            loop = asyncio.get_running_loop()
            self._file_writer = functools.partial(loop.run_in_executor, _th_pool, fd.write)
            yield

    @property
    def seek_pos(self):
        return self._seek

    async def close(self, *args):
        return self.fd.close()
