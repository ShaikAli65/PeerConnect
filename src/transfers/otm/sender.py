import asyncio
import mmap
from pathlib import Path

import umsgpack

from src.avails import OTMSession, RemotePeer, WireData, constants as const, useables as use
from src.core import get_this_remote_peer
from src.transfers import HEADERS
from src.transfers.files._fileobject import FileItem, calculate_chunk_size
from src.transfers.otm.relay import OTMFilesRelay, OTMPalmTreeProtocol


class FilesSender:

    def __init__(self, file_list: list[Path | str], peers: list[RemotePeer], timeout):
        self.peer_list = peers
        self.file_items = [FileItem(file_path, 0) for file_path in file_list]
        self.timeout = timeout

        self.session = self._make_session()
        self.palm_tree = OTMPalmTreeProtocol(
            get_this_remote_peer(),
            self.session,
            peers,
        )

        self.relay: OTMFilesRelay = self.palm_tree.relay

    def _make_session(self):
        return OTMSession(
            originate_id=get_this_remote_peer().peer_id,
            session_id=use.get_unique_id(),
            key=use.get_unique_id(),
            fanout=const.DEFAULT_GOSSIP_FANOUT,  # make this linearly scalable based on file count and no.of recipients
            file_count=len(self.file_items),
            adjacent_peers=[],
            link_wait_timeout=self.timeout,
            chunk_size=calculate_chunk_size(sum(file.size for file in self.file_items)),
        )

    async def start(self):
        #
        # call order :
        # inform peers
        # relay.session_init
        # update states
        # trigger_spanning_formation
        #
        inform_req = self._create_inform_packet()
        yield await self.palm_tree.inform_peers(inform_req)
        await self.relay.session_init()
        yield await self.palm_tree.update_states()

        # setting this future, as we are the actual sender
        self.palm_tree.relay._parent_link_fut.set_result(None)

        yield await self.palm_tree.trigger_spanning_formation()

        # ========> debug
        print_signal = WireData(
            header='gossip_print_every_onces_states',
            msg_id=get_this_remote_peer().peer_id,
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

    def _create_inform_packet(self):
        return WireData(
            header=HEADERS.OTM_FILE_TRANSFER,
            msg_id=get_this_remote_peer().peer_id,
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

    @property
    def id(self):
        return self.session.session_id
