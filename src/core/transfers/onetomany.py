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

import asyncio
import collections
import itertools
import mmap
from pathlib import Path
from typing import Generator, Optional, override

import umsgpack

from src.avails import OTMSession, RemotePeer, WireData, const, use
from src.core.transfers.palm_tree import HEADERS, PalmTreeLink, PalmTreeProtocol, PalmTreeRelay, TreeLink
from src.core.transfers.fileobject import PeerFilePool, FileItem
from src.core import get_this_remote_peer


class OTMLink(PalmTreeLink):
    def __init__(self, a: tuple, b: tuple, peer_id, connection=None, link_type: int = PalmTreeLink.PASSIVE,*, buffer_len):
        super().__init__(a, b, peer_id, connection, link_type)
        self.buffer = asyncio.Queue(maxsize=buffer_len)

    @override
    async def recv(self, length):
        return await super().recv(length)

    @override
    async def send(self, data):
        await super().send(data)


class OTMFilesRelay(PalmTreeRelay):
    # :todo: try using temporary-spooled files
    def __init__(self, session, passive_endpoint_addr: tuple[str, int] = None,
                 active_endpoint_addr: tuple[str, int] = None):
        super().__init__(session, passive_endpoint_addr, active_endpoint_addr)
        self._read_link = None
        self.file_receiver = OTMFilesReceiver(session, self)
        # this is a generator `:method: OTMFilesReceiver.data_receiver` that takes byte-chunk inside it
        self.chunk_recv_handler = self.file_receiver.data_receiver()

        # self.recv_buffer = bytearray(const.MAX_OTM_BUFFERING)
        # self.recv_buffer_view = memoryview(self.recv_buffer)
        self.recv_buffer_queue = collections.deque(maxlen=const.MAX_OTM_BUFFERING)
        self.chunk_counter = 0

    async def start_readside(self):
        """
        Starts reading and forwarding part of the protocol if called
        this function is not called when this relay is the one who is sending the files to others
        """
        await self.set_up()
        await self._recv_file_metadata()
        next(self.chunk_recv_handler)  # starting the reverse generator
        await self._start_reader()

    @override
    async def gossip_tree_check(self, tree_check_packet: WireData, addr):
        await super().gossip_tree_check(tree_check_packet, addr)
        # this means:
        # link is accepted
        # this is the link we are reading from, for data
        #
        self._read_link = await self._parent_link_fut
        # the only expected case this being None is when this peer is the actual sender

    @override
    def _make_update_stream_link_packet(self):
        h = WireData(
            header=HEADERS.OTM_UPDATE_STREAM_LINK,
            _id=get_this_remote_peer().id,
            session_id=self.session.session_id,
            peer_addr=self.passive_endpoint_addr,
        )
        return bytes(h)

    def set_up(self):
        return super().session_init()

    async def _start_reader(self):
        read_conn = self._read_link.connection
        while True:
            try:
                chunk_detail = await self._read_link.recv(1)
                if chunk_detail == b'0':
                    # we received an empty chunk that need to be addressed later
                    self._empty_chunk_received()
                    self.chunk_counter += 1
                    continue

                whole_chunk = await read_conn.arecv(self.session.chunk_size)

                if not whole_chunk:
                    self._end_of_transfer()

                self.chunk_counter += 1
                self.chunk_recv_handler.send(whole_chunk)
                await self._forward_chunk(whole_chunk)

            except OSError as e:
                self.print_state(f"got an os error at {use.func_str(self._start_reader)}", e)
                what = await self._read_link_broken()
                if not what:
                    self._end_of_transfer()
                    return
                else:
                    self._read_link = what
                    read_conn = what.connection

    def _empty_chunk_received(self):
        pass

    async def _read_link_broken(self) -> Optional[TreeLink]:
        # :todo: write the logic that handles missing chunks in the time period of link broken and attached
        await super()._parent_link_broken()
        return await self._parent_link_fut

    def _end_of_transfer(self):

        ...

    async def _forward_chunk(self, chunk: bytes):
        timeout = self.session.link_wait_timeout

        is_forwarded_to_atleast_once = False
        # await self._is_connection_to_atleast_one_link_made
        # this future has the first link that made a connection, ignoring the result for now
        for link in self._get_forward_links():
            try:
                await asyncio.wait_for(link.connection.asendall(chunk), timeout)
                is_forwarded_to_atleast_once = True
            except TimeoutError:
                link.status = PalmTreeLink.LAGGING  # mark this link as lagging

        if is_forwarded_to_atleast_once is False:
            await asyncio.sleep(timeout)  # add further edge case logic
            # :todo: heavy recursion bug need to be reviewed
            # temporarily yielding back to wait for incoming/outgoing connections
            await self._forward_chunk(chunk)

    async def send_file_metadata(self, data):
        # this is the first step of a file transfer
        # await self._read_link.connection.arecv(self.session.chunk_size)
        await self._forward_chunk(b'\x01' + data)

    async def _recv_file_metadata(self):
        self._read_link = await self._parent_link_fut
        # this future is set when a sender makes a connection

        files_metadata: bytes = await self._read_link.connection.arecv(self.session.chunk_size + 1)
        status, files_metadata = files_metadata[:1], files_metadata[1:]

        self.file_receiver.update_metadata(files_metadata)

        await self.send_file_metadata(files_metadata)

    async def send_file_chunk(self, chunk):
        await self._forward_chunk(chunk)

    async def otm_add_stream_link(self, connection, hand_shake):
        await super().gossip_add_stream_link(connection, hand_shake)


class OTMPalmTreeProtocol(PalmTreeProtocol):
    mediator_class = OTMFilesRelay


class OTMFilesSender:

    def __init__(self, file_list: list[Path | str], peers: list[RemotePeer], timeout):
        self.peer_list = peers
        self.file_items = [FileItem(file_path, 0) for file_path in file_list]
        self.timeout = timeout

        self.session = self.make_session()
        self.palm_tree = OTMPalmTreeProtocol(
            get_this_remote_peer(),
            self.session,
            peers,
        )

        self.relay: OTMFilesRelay = self.palm_tree.relay

    def make_session(self):
        return OTMSession(
            originate_id=get_this_remote_peer().id,
            session_id=use.get_unique_id(),
            key=use.get_unique_id(),
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
        # relay.session_init
        # update states
        # trigger_spanning_formation
        #
        inform_req = self.create_inform_packet()
        yield await self.palm_tree.inform_peers(inform_req)
        await self.relay.session_init()
        yield await self.palm_tree.update_states()

        # setting this future, as we are the actual sender
        self.palm_tree.relay._parent_link_fut.set_result(None)

        yield await self.palm_tree.trigger_spanning_formation()

        # ========> debug
        print_signal = WireData(
            header='gossip_print_every_onces_states',
            _id=get_this_remote_peer().id,
        )
        await asyncio.sleep(1)  # debug
        await self.relay.gossip_print_every_onces_states(print_signal, tuple())
        # ========> debug

        yield await self.relay.send_file_metadata(self._make_file_metadata())

        for file_item in self.file_items:
            yield await self.send_file(file_item)
        """
        References:
        https://en.wikipedia.org/wiki/Leaky_bucket
        https://en.wikipedia.org/wiki/Token_bucket        
        https://en.wikipedia.org/wiki/Generic_cell_rate_algorithm
        
        """

    async def send_file(self, file_item):
        chunk_size = self.session.chunk_size
        with open(file_item.path, 'rb') as f:
            seek = file_item.seeked
            f_mapped = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for offset in range(seek, file_item.size, chunk_size):
                chunk = f_mapped[offset: offset + chunk_size]
                await self.relay.send_file_chunk(chunk)

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
            chunk_size=const.MAX_DATAGRAM_RECV_SIZE,
        )

    def _make_file_metadata(self):
        return umsgpack.dumps([bytes(x) for x in self.file_items])


class OTMFilesReceiver(asyncio.BufferedProtocol):

    def __init__(self, session, relay):
        self.file_items = []
        self.session: OTMSession = session
        self.relay = relay
        self.current_file_item = 0  # index pointing to file item that is currently under receiving
        self.chunk_count = 0
        self._left_out_chunk = bytearray()

    def update_metadata(self, metadata_packet):
        self.file_items = self._load_file_metadata(metadata_packet)
        print("recieved file items", self.file_items)
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

    def data_receiver(self) -> Generator[None, bytes, None]:
        sliced_enumeration = itertools.islice(enumerate(self.file_items), self.current_file_item, None)
        left_over = bytearray()
        for i, file_item in sliced_enumeration:
            self.current_file_item = i
            with open(file_item.path, 'w+b') as file:
                while True:
                    chunk = yield
                    total_chunk_view = memoryview(left_over + chunk)
                    to_write_size = min(len(total_chunk_view), file_item.size - file.tell())
                    file.write(total_chunk_view[: to_write_size])
                    file_item.seeked = to_write_size
                    left_over = bytearray(total_chunk_view[to_write_size:])
                    # Break if the file is fully written
                    if file.tell() >= file_item.size:
                        break

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
