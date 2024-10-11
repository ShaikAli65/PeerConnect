import asyncio
from dataclasses import dataclass

from src.avails import RemotePeer, WireData, const, unpack_datagram
from .. import get_this_remote_peer


class OTMBytesSender:
    def __init__(self, data: bytes, peers: list[RemotePeer], session_id):
        self.data = data
        self.peer_list = peers
        self.session_id = session_id
        self.confirmed_peers = None


class OTMBytesReceiver:
    def __init__(self, session):
        ...
