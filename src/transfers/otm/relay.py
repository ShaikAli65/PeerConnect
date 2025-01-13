import asyncio
import collections
from typing import Optional, override

from src.avails import WireData, constants as const, useables as use
from src.core import get_this_remote_peer
from src.transfers import HEADERS
from src.transfers.otm.palm_tree import PalmTreeLink, PalmTreeProtocol, PalmTreeRelay, TreeLink
from src.transfers.otm.receiver import FilesReceiver


class OTMFilesRelay(PalmTreeRelay):
    # :todo: try using temporary-spooled files
    def __init__(
            self,
            session,
            file_receiver,
            passive_endpoint_addr,
            active_endpoint_addr,
    ):
        super().__init__(session, passive_endpoint_addr, active_endpoint_addr)
        self._read_link = None
        self.file_receiver: FilesReceiver = file_receiver
        # this is a generator `:method: OTMFilesReceiver.data_receiver` that takes byte-chunk inside it
        self.chunk_recv_gen = self.file_receiver.data_receiver()
        self._forward_limiter = asyncio.Semaphore(self.session.fanout)
        self.recv_buffer_queue = collections.deque(maxlen=const.MAX_OTM_BUFFERING)
        self.chunk_counter = 0

    async def start_read_side(self):
        """Starts reading and forwarding part of the protocol

        Not called when this relay is the one who is sending the files to others

        """
        await super().session_init()
        await self._recv_file_metadata()
        next(self.chunk_recv_gen)  # starting the reverse generator
        await self._start_reader()

    async def _recv_file_metadata(self):
        self._read_link = await self._parent_link_fut
        # this future is set when a sender makes a connection

        files_metadata: bytes = await self._read_link.recv(self.session.chunk_size)

        self.file_receiver.update_metadata(files_metadata)

        await self.send_file_metadata(files_metadata)

    async def _start_reader(self):
        recv_bytes = self._read_link.recv
        chunk_size = self.session.chunk_size
        while True:
            try:
                whole_chunk = await recv_bytes(chunk_size)
                if not whole_chunk:
                    await self._read_link_broken()

                self.chunk_counter += 1
                self.chunk_recv_gen.send((self.chunk_counter, whole_chunk))
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

    async def _read_link_broken(self) -> Optional[TreeLink]:
        # :todo: write the logic that handles missing chunks in the time period of link broken and attached
        await super()._parent_link_broken()
        return await self._parent_link_fut

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
            msg_id=get_this_remote_peer().peer_id,
            session_id=self.session.session_id,
            peer_addr=self.passive_endpoint_addr,
        )
        return bytes(h)

    def _end_of_transfer(self):

        ...

    async def _forward_chunk(self, chunk: bytes):
        async with self._forward_limiter:
            for link in self._get_forward_links():
                try:
                    if link.is_lagging:
                        print(f"found {link} lagging ignoring")
                        continue

                    await asyncio.wait_for(link.send(chunk), self.session.link_wait_timeout)
                except TimeoutError:
                    link.status = TreeLink.LAGGING

    async def send_file_metadata(self, data):
        # this is the first step of a file transfer
        # await self._read_link.connection.arecv(self.session.chunk_size)
        await self._forward_chunk(data)

    async def send_file_chunk(self, chunk):
        await self._forward_chunk(chunk)

    async def otm_add_stream_link(self, connection, hand_shake):
        await super().gossip_add_stream_link(connection, hand_shake)


class OTMPalmTreeProtocol(PalmTreeProtocol):
    mediator_class = OTMFilesRelay


class OTMLink(PalmTreeLink):
    def __init__(self, a: tuple, b: tuple, peer_id, connection=None, link_type: int = PalmTreeLink.PASSIVE, *,
                 buffer_len):
        super().__init__(a, b, peer_id, connection, link_type)
        self.buffer = asyncio.Queue(maxsize=buffer_len)
