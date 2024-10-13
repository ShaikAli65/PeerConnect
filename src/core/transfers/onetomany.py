from pathlib import Path

from src.avails import OTMSession, RemotePeer, WireData, const
from . import HEADERS, PalmTreeRelay, PalmTreeProtocol
from .. import get_this_remote_peer
from ...avails.useables import get_unique_id


"""
    All the classes here are closely coupled with 
    PalmTreeProtocol in gossip protocols 
    here's the plan
    . file manager gets command to set up file transfer
    . OTMFilesRelay gets called for setup
    . OTMFilesReceiver (which follows asyncio's Buffered Protocol ??) reference is passed into OTMRelay 
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
        self.file_list = file_list
        self.timeout = timeout
        self.palm_tree = PalmTreeProtocol(
            get_this_remote_peer(),
            self.session,
            peers,
            OTMFilesRelay,
        )

    def make_session(self):
        return OTMSession(
            originater_id=get_this_remote_peer().id,
            session_id=get_unique_id(str),
            key=get_unique_id(str),
            fanout=const.DEFAULT_GOSSIP_FANOUT,  # make this linearly scalable based on file count and no.of recipients
            file_count=len(self.file_list),
            adjacent_peers=[],
            link_wait_timeout=self.timeout
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
        self.palm_tree.mediator.start_session()
        yield self.palm_tree.update_states()
        yield self.palm_tree.trigger_spanning_formation()

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


class OTMFilesReceiver:
    def __init__(self, session):
        ...


class OTMFilesRelay(PalmTreeRelay):
    ...
