import array
import asyncio
from bisect import bisect_left
from contextlib import ExitStack, asynccontextmanager
from itertools import islice
from typing import BinaryIO, Generator

import umsgpack

from src.avails import OTMSession, const
from src.transfers._fileobject import FileItem
from src.transfers.otm.relay import OTMFilesRelay


class FilesReceiver(asyncio.BufferedProtocol):

    def __init__(self, session, passive_endpoint, active_endpoint):
        self.file_items = []
        self.session: OTMSession = session
        self.relay = OTMFilesRelay(
            self,
            session,
            passive_endpoint,
            active_endpoint,
        )
        self._relay_task = asyncio.create_task(self.relay.start_read_side())
        self.current_file_index = 0  # index pointing to file item that is currently under transfer
        self.chunk_count = 0
        self._left_out_chunk = bytearray()
        self._file_sizes_summed = None
        self._file_descriptors: dict[FileItem, BinaryIO] = {}
        self.total_byte_count = None

    def update_metadata(self, metadata_packet):
        self._load_files_metadata(metadata_packet)
        print("received file items", self.file_items)

        # page handle.send_status_data(StatusMessage())

    def _load_files_metadata(self, file_data: bytes):
        # a list of bytes
        loaded_data = umsgpack.loads(file_data)
        self.file_items = [
            FileItem.load_from(file_item, const.PATH_DOWNLOAD)
            for file_item in loaded_data
        ]

        sums = [self.file_items[0].size]
        for file_item in islice(self.file_items, 1, len(self.file_items)):
            sums.append(sums[-1] + file_item.size)

        self._file_sizes_summed = array.array('I', sums)
        self.total_byte_count = sums[-1]

    async def _write_chunk(self, chunk):
        file_item = self.file_items[self.current_file_index]
        writer = self._file_descriptors[file_item].write
        chunked_chunk = chunk[0: min(file_item.size - file_item.seeked, len(chunk))]
        writer(chunked_chunk)  # possible: Storage Unavailable
        file_item.seeked += len(chunked_chunk)

        if len(chunk) - len(chunked_chunk) > 0:
            self.current_file_index += 1
            if self.current_file_index == len(self.file_items):
                return  # end of transfer

            # we got a chunk that belong to two different files
            await self._write_chunk(chunk[len(chunked_chunk):])

    async def data_receiver(self) -> Generator[None, tuple[int, bytes], None]:

        with self._open_files():
            while self.current_file_index <= len(self.file_items):
                chunk = yield
                self._align_corresponding_chunk()
                await self._write_chunk(chunk)

    @asynccontextmanager
    async def _open_files(self):
        async with ExitStack() as exit_stack:
            for file in self.file_items:
                exit_stack.enter_context(fd := open(file.path, 'wb+'))
                self._file_descriptors[file] = fd
            yield

    def _align_corresponding_chunk(self):

        # Internals:
        # we treat all the bytes related to different files as a single byte stream
        # upon reading different chunks and treating them as a single stream
        # this code dynamically writes data into corresponding file on disk
        # based on the metadata received upfront

        #     chunk_size = 2B
        #     % 5 files with these sizes
        #
        #     -----  ------- ------ ------- ------
        #     | 1B | | 10B | | 5B | | 30B | | 9B |
        #     -----  ------- ------ ------- ------

        # say we got chunk_count = 8
        # chunk alignment::
        # chunk belongs to file no. 3

        # sums::
        #     ------  ------- ------- ------- -------
        #     | 1B |  | 11B | | 16B | | 46B | | 55B |
        #     ------  ------- ------- ------- -------
        #     ---------------------------------------
        #        1       2       3       4       5
        #     ---------------------------------------
        #     ---------------------------------------
        #     //////////////////////16B
        #     ---------------------------------------

        #   8 * chunk_size = 16B
        #   we get f seek of a combined byte stream
        #   now writing chunk at seek pointer 16 of length chunk_len
        _i = bisect_left(self._file_sizes_summed, self.relay.chunk_counter * self.session.chunk_size)
        self.current_file_index = _i

    def close(self):
        self._relay_task.cancel()

    @property
    def id(self):  # required by file manager for bookkeeping
        return self.session.session_id
