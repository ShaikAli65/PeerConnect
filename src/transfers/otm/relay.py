import asyncio
import collections
from contextlib import aclosing
from typing import TYPE_CHECKING, override

from src.avails import WireData, constants as const
from src.avails.useables import LONG_INT, recv_int
from src.core import get_this_remote_peer
from src.transfers import HEADERS
from src.transfers.otm.palm_tree import PalmTreeLink, PalmTreeProtocol, PalmTreeRelay, TreeLink


class OTMFilesRelay(PalmTreeRelay):
    # :todo: try using temporary-spooled files
    if TYPE_CHECKING:
        from src.transfers.otm.receiver import FilesReceiver
        file_receiver: FilesReceiver

    def __init__(
            self,
            file_receiver,
            session,
            passive_endpoint_addr,
            active_endpoint_addr,
    ):
        super().__init__(session, passive_endpoint_addr, active_endpoint_addr)
        self._read_link = None
        self.file_receiver = file_receiver
        # this is a generator `:method: OTMFilesReceiver.data_receiver` that takes byte-chunk inside it
        self.chunk_recv_gen = self.file_receiver.data_receiver()
        self._forward_limiter = asyncio.Semaphore(self.session.fanout)
        self.recv_buffer_queue = collections.deque(maxlen=const.MAX_OTM_BUFFERING)
        self.chunk_counter = 0
        self.missing_chunks = []  # type:list[tuple[int,int]]

    async def start_read_side(self):
        """Starts reading and forwarding part of the protocol

        Not called when this relay is the one who is sending the files to others

        """
        await super().session_init()
        await self._recv_file_metadata()

        async with aclosing(self.chunk_recv_gen) as chunk_reciever:
            await anext(chunk_reciever)  # starting the reverse generator
            await self._start_reader()

    async def _recv_file_metadata(self):
        self._read_link = await self._parent_link_fut
        # this future is set when a sender makes a connection

        files_metadata = await self._read_link.recv(self.session.chunk_size)

        self.file_receiver.update_metadata(files_metadata)

        await self.send_file_metadata(files_metadata)

    async def send_file_metadata(self, data):
        # this is the first step of a file transfer
        await self._forward_chunk(data)

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

    async def _start_reader(self):
        """
        Continuously reads data from the link in chunks and forwards them.
        Handles errors and broken links appropriately.
        """
        chunk_size = self.session.chunk_size
        total_bytes_len = self.file_receiver.total_byte_count
        receiver_generator = self.chunk_recv_gen.asend

        while True:
            try:
                chunk = await self._read_link.recv(chunk_size)
            except OSError as e:
                # Handle any OS-level errors during read
                self.print_state("OS error encountered while reading link", e)
                await self._handle_read_link_broken()
                continue

            if not chunk:
                await self._handle_read_link_broken()
                continue

            await receiver_generator((self.chunk_counter, chunk))
            await self._forward_chunk(chunk)
            if self.chunk_counter * len(chunk) >= total_bytes_len:
                # end of bulk transfer, now filling up any chunks missed during link broken states
                await self.fill_partial_chunks()
                return
            self.chunk_counter += 1

    async def _handle_read_link_broken(self):
        """
        Logic to handle scenarios when the read link is broken.
        """
        # TODO: Implement missing chunk handling logic during broken/reattached state

        # Notify parent link about the broken state
        # underlying algorithms make sure that we get a valid link

        await super()._parent_link_broken()

        # Re-establish the read link
        self._read_link = await self._parent_link_fut
        try:
            current_counter = await recv_int(self._read_link.recv, LONG_INT)
        except ConnectionResetError:  # again broken
            return await self._handle_read_link_broken()

        if current_counter == self.chunk_counter:
            return  # we are luckly that states are in sync

    async def fill_partial_chunks(self):
        ...

    def _end_of_transfer(self):

        ...

    async def send_file_chunk(self, chunk):
        return await self._forward_chunk(chunk)

    async def otm_add_stream_link(self, connection, hand_shake):
        return await super().gossip_add_stream_link(connection, hand_shake)

    @override
    async def gossip_tree_check(self, tree_check_packet: WireData, addr):
        await super().gossip_tree_check(tree_check_packet, addr)
        # this means:
        # link is accepted
        # this is the link we are reading from, for data
        #
        self._read_link = await self._parent_link_fut
        # the only expected case this being None, is when this peer is the actual sender

    @override
    def _make_update_stream_link_packet(self):
        h = WireData(
            header=HEADERS.OTM_UPDATE_STREAM_LINK,
            msg_id=get_this_remote_peer().peer_id,
            session_id=self.session.session_id,
            peer_addr=self.passive_endpoint_addr,
        )
        return bytes(h)


class OTMPalmTreeProtocol(PalmTreeProtocol):
    mediator_class = OTMFilesRelay
    relay: OTMFilesRelay


class OTMLink(PalmTreeLink):
    def __init__(self, a: tuple, b: tuple, peer_id, connection=None, link_type: int = PalmTreeLink.PASSIVE, *,
                 buffer_len):
        super().__init__(a, b, peer_id, connection, link_type)
        self.buffer = asyncio.Queue(maxsize=buffer_len)
