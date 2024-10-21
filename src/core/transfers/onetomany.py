import asyncio
import collections
from pathlib import Path
from typing import Optional

import umsgpack

from src.avails import OTMSession, RemotePeer, WireData, const
from . import FileItem, HEADERS, PalmTreeLink, PalmTreeProtocol, PalmTreeRelay, PeerFilePool
from .. import get_this_remote_peer
from ..discover import override
from ...avails.useables import get_unique_id, wrap_with_tryexcept

"""
    All the classes here are closely coupled with 
    PalmTreeProtocol in gossip protocols 
    here's the plan
    . file manager gets command to set up file transfer
    . OTMFilesRelay gets called for setup
    . OTMFilesReceiver (which follows asyncio.Buffered Protocol ??) reference is passed into OTMRelay 
    . OTMFilesReceiver does not need a reference to OTMRelay cause it does nothing but receives file data ??
      no need to interact with Relay cause data is flown RELAY -> OTM FILES RECV, not the other way around
    . OTMFilesSender indeed require a reference to underlying relay to feed data into 
    . all the connection switching overhead and data loss to be decided
    . n file chucks are to be kept in memory for data relay loss
"""


class OTMFilesSender:

    def __init__(self, file_list: list[Path | str], peers: list[RemotePeer], timeout):
        self.peer_list = peers
        self.session = self.make_session()
        self.file_items = [FileItem(file_path, 0) for file_path in file_list]
        self.timeout = timeout
        self.palm_tree = PalmTreeProtocol(
            get_this_remote_peer(),
            self.session,
            peers,
            OTMFilesRelay,
        )
        self.relay: OTMFilesRelay = self.palm_tree.relay
        self.files_metadata_bytes = self._make_file_metadata(file_list)

    def make_session(self):
        return OTMSession(
            originater_id=get_this_remote_peer().id,
            session_id=get_unique_id(str),
            key=get_unique_id(str),
            fanout=const.DEFAULT_GOSSIP_FANOUT,  # make this linearly scalable based on file count and no.of recipients
            file_count=len(self.file_items),
            adjacent_peers=[],
            link_wait_timeout=self.timeout,
            chunk_size=PeerFilePool.calculate_chunk_size(sum(file.size for file in self.file_items)),
        )

    async def start(self):
        #
        # call order :
        # inform peers
        # self.mediator.start_session
        # update states
        # trigger_spanning_formation
        #
        inform_req = self.create_inform_packet()
        yield self.palm_tree.inform_peers(inform_req)
        await self.palm_tree.relay.session_init()
        yield self.palm_tree.update_states()
        yield await self.palm_tree.trigger_spanning_formation()
        yield await self.relay.send_file_metadata(self.files_metadata_bytes)
        for file_item in self.file_items:
            yield await self.send_file(file_item)

    async def send_file(self, file_item):
        ...

    def create_inform_packet(self):
        return WireData(
            header=HEADERS.OTM_FILE_TRANSFER,
            _id=get_this_remote_peer().id,
            protocol1=str(self.__class__),
            protocol2=str(self.palm_tree.__class__),
            session_id=self.session.session_id,
            key=self.session.key,
            fanout=self.session.fanout,
            link_wait_timeout=self.session.link_wait_timeout,
            adjacent_peers=self.session.adjacent_peers,
            file_count=self.session.file_count,
        )

    @staticmethod
    def _make_file_metadata(file_list):
        return umsgpack.dumps(file_list)


class OTMFilesReceiver(asyncio.BufferedProtocol):

    def __init__(self, session, relay):
        self.file_items = []
        self.session = session
        self.relay = relay
        self.current_file_item = 0  # index pointing to file item that is currently under receiving
        self.chunk_count = 0

    def update_metadata(self, metadata_packet):
        self.file_items = self._load_file_metadata(metadata_packet)
        # page handle.send_status_data(StatusMessage())

    @staticmethod
    def _load_file_metadata(file_data: bytes):
        # a list of bytes
        loaded_data = umsgpack.loads(file_data)
        file_items = [
            FileItem.load_from(file_item, const.PATH_DOWNLOAD)
            for file_item in loaded_data
        ]
        return file_items

    def data_received(self, buffer_queue):
        current_item = self._get_current_item()
        left_out_chunk = bytearray()
        with open(current_item.path, 'a+b') as f:
            for chunk in buffer_queue:
                total_chunk_view = memoryview(left_out_chunk + chunk)
                while total_chunk_view:
                    to_write_size = min(len(total_chunk_view), current_item.size - f.tell())
                    if to_write_size > 0:
                        f.write(total_chunk_view[:to_write_size])
                        total_chunk_view = total_chunk_view[to_write_size:]
                    else:
                        # Move to the next file item if current one is fully written
                        self._update_file_item()
                        current_item = self._get_current_item()
                        f.close()
                        f = open(current_item.path, 'a+b')

                self.chunk_count += 1  # Only count after full write

    def _get_current_item(self) -> FileItem:
        return self.file_items[self.current_file_item]

    def _update_file_item(self):
        self.current_file_item += 1


class OTMFilesRelay(PalmTreeRelay):
    # :todo: try using temporary spooled files
    def __init__(self, session, passive_endpoint_addr: tuple[str, int] = None,
                 active_endpoint_addr: tuple[str, int] = None):
        super().__init__(session, passive_endpoint_addr, active_endpoint_addr)
        self._read_link = None
        self.file_receiver = OTMFilesReceiver(session, self)
        # self.recv_buffer = bytearray(const.MAX_OTM_BUFFERING)
        # self.recv_buffer_view = memoryview(self.recv_buffer)
        self.recv_buffer_queue = collections.deque(const.MAX_OTM_BUFFERING)
        self.chunk_counter = 0

    async def start(self):
        await self.set_up()
        metadata_packet = await self._recv_file_metadata()
        self.file_receiver.update_metadata(metadata_packet)
        await self.start_reader()

    @override
    def gossip_tree_check(self, tree_check_packet: WireData, addr):
        what = super().gossip_tree_check(tree_check_packet, addr)
        if what is True:
            # this means:
            # link is accepted
            # this is the link we are reading from, for data
            self._read_link = self.active_links[tree_check_packet.id]

    async def set_up(self):
        ...

    async def start_reader(self):
        read_conn = self._read_link.connection
        while True:
            try:
                whole_chunk = await read_conn.arecv(self.session.chunk_size + 1)
                if not whole_chunk:
                    self._end_of_transfer()
                chunk_detail, chunk = whole_chunk[:1], whole_chunk[1:]
                self._update_buffer(chunk)
                self._may_be_update_receiver()
                await self._forward_chunk(whole_chunk)
            except OSError as e:
                print("got an os error", e)
                what = await self._read_link_broken()
                if not what:
                    self._end_of_transfer()
                    return
                else:
                    self._read_link = what
                    read_conn = what.connection

    async def _read_link_broken(self) -> Optional[PalmTreeLink]:
        # :todo: write the logic that handles missing chunks in the time period of link broken and attached

        ...

    def _update_buffer(self, chunk):
        # self.recv_buffer_view[self.chunk_counter: self.chunk_counter + self.session.chunk_size] = chunk
        self.recv_buffer_queue.append(chunk)
        self.chunk_counter += 1

    def _may_be_update_receiver(self):
        if self.chunk_counter % const.MAX_OTM_BUFFERING == 0:
            # we filled queue, time to empty it
            self.file_receiver.data_received(self.recv_buffer_queue)
            self.recv_buffer_queue.clear()

    def _end_of_transfer(self):

        ...

    async def _forward_chunk(self, chunk: bytes):
        timeout = self.session.link_wait_timeout
        for link in self._get_forward_links():
            try:
                await asyncio.wait_for(link.connection.asendall(chunk), timeout)
            except TimeoutError:
                link.status = PalmTreeLink.LAGGING  # mark this link as lagging

    async def send_file_metadata(self, data):
        # this is the first step of a file transfer
        await self._read_link.connection.arecv(self.session.chunk_size)
        await self._forward_chunk(b'\x01' + data)

    async def _recv_file_metadata(self):
        files_metadata = await self._read_link.connection.arecv(self.session.chunk_size)
        f = wrap_with_tryexcept(self.send_file_metadata, files_metadata)
        asyncio.create_task(f)
        return files_metadata
