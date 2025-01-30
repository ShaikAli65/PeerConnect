import array
import asyncio
import itertools
from bisect import bisect_left
from typing import Generator

import umsgpack

from src.avails import OTMSession, const
from src.transfers.files._fileobject import FileItem
from src.transfers.otm.relay import OTMFilesRelay


class FilesReceiver(asyncio.BufferedProtocol):

    def __init__(self, session, passive_endpoint, active_endpoint):
        self.file_items = []
        self.session: OTMSession = session
        self.relay = OTMFilesRelay(
            session,
            self,
            passive_endpoint,
            active_endpoint,
        )
        self._relay_task = asyncio.create_task(self.relay.start_read_side())
        self.current_file_index = 0  # index pointing to file item that is currently under receiving
        self.chunk_count = 0
        self._left_out_chunk = bytearray()
        self.file_sizes_summed = None

    def update_metadata(self, metadata_packet):
        self._load_file_metadata(metadata_packet)
        print("recieved file items", self.file_items)
        # page handle.send_status_data(StatusMessage())

    def _load_file_metadata(self, file_data: bytes):
        # a list of bytes
        loaded_data = umsgpack.loads(file_data)
        self.file_items = [
            FileItem.load_from(file_item, const.PATH_DOWNLOAD)
            for file_item in loaded_data
        ]
        current_sum = self.file_items[0]
        sums = [current_sum]
        for file_item in self.file_items[1:]:
            current_sum += file_item.size
            sums.append(current_sum)
        self.file_sizes_summed = array.array('I', sums)

    def data_receiver(self) -> Generator[None, tuple[int, bytes], None]:
        sliced_enumeration = itertools.islice(enumerate(self.file_items), self.current_file_index, None)
        left_over = bytearray()

        def BinarySearch(sums, x):
            _i = bisect_left(sums, x)
            if _i != len(sums) and sums[_i] == x:
                return _i

        while True:
            seek, chunk = yield

            #
        # for i, file_item in sliced_enumeration:
        #     self.current_file_index = i
        #     with open(file_item.path, 'w+b') as file:
        #         while True:
        #             seek, chunk = yield
        #             total_chunk_view = memoryview(left_over + chunk)
        #             to_write_size = min(len(total_chunk_view), file_item.size - file.tell())
        #             file.write(total_chunk_view[: to_write_size])
        #             file_item.seeked = to_write_size
        #             left_over = bytearray(total_chunk_view[to_write_size:])
        #             # Break if the file is fully written
        #             if file.tell() >= file_item.size:
        #                 break

    @property
    def id(self):  # required by file manager for book keeping
        return self.session.session_id

    def close(self):
        self._relay_task.cancel()

    #     naive code to laugh upon

    # def data_received(self, buffer_queue):
    #     current_item = self._get_current_item()
    #     file = None
    #     try:
    #         file = open(current_item.path, 'a+b')
    #         for chunk in buffer_queue:
    #             # total_chunk_view = memoryview(self._left_out_chunk + chunk)
    #             total_chunk_view = memoryview(chunk)
    #             while total_chunk_view:
    #                 to_write_size = min(len(total_chunk_view), current_item.size - file.tell())
    #                 if to_write_size > 0:
    #                     file.write(total_chunk_view[:to_write_size])
    #                     total_chunk_view = total_chunk_view[to_write_size:]
    #                 else:
    #                     # Move to the next file item if current one is fully written
    #                     self._update_file_item()
    #                     current_item = self._get_current_item()
    #                     # self._left_out_chunk = total_chunk_view
    #
    #                     file.close()
    #                     file = open(current_item.path, 'a+b')
    #
    #             self.chunk_count += 1  # Only count after full write
    #     finally:
    #         if file:
    #             file.close()
    #
    # def _get_current_item(self) -> FileItem:
    #     return self.file_items[self.current_file_item]
    #
    # def _update_file_item(self):
    #     self.current_file_item += 1
