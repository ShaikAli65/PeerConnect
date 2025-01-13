"""
    All the classes here are closely coupled with
    PalmTreeProtocol in gossip protocols
    here's the plan
    . file manager gets command to set up file transfer
    . OTMFilesRelay gets called for status_setup
    . OTMFilesReceiver (which follows asyncio.Buffered Protocol ??) reference is passed into OTMRelay
    . OTMFilesReceiver does not need a reference to OTMRelay cause it does nothing but receives file data ??
      no need to interact with Relay cause data is flown RELAY -> OTM FILES RECV, not the other way around
    . OTMFilesSender indeed require a reference to underlying relay to feed data into
    . all the connection switching overhead and data loss to be decided
    . n file chucks are to be kept in memory for data relay loss
"""
from .receiver import FilesReceiver
from .sender import FilesSender
