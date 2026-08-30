import asyncio
import enum
import random
import logging
from asyncio import Future
from collections import defaultdict
from dataclasses import dataclass
from typing import NamedTuple, Optional

from src.avails import RemotePeer, WireData, const, use
from src.avails.wire import PalmTreeSession

logger = logging.getLogger(__name__)


def first_pool_of_peers(peer_list: list[RemotePeer], pool_size: int):
    return random.choices(peer_list, k=pool_size)


@dataclass
class PalmTreeConfig:
    session: PalmTreeSession
    max_fanout: int = 3
    request_timeout: int = 3
    req_retries: int = 3


class PalmTreeOps(enum.Enum):
    SendPassiveMessage = enum.auto()
    SendActiveMessage = enum.auto()
    SendPing = enum.auto()
    Downgrade = enum.auto()
    ChunkRecv = enum.auto()
    ChunkRecvFailed = enum.auto()

    ChunkIHave = enum.auto()
    ChunkSend = enum.auto()
    ChunkSendFailed = enum.auto()


class PalmTreeCommand(NamedTuple):
    op: PalmTreeOps
    peer: RemotePeer
    data: dict | str | None = None


class PeerCommState(enum.Enum):
    ActiveLinkRequested = enum.auto()
    PassiveLinkActive = enum.auto()
    ActiveLinkActive = enum.auto()
    Errored = enum.auto()


# class ChunkSendStatus(enum.Enum):
#     InProgress = enum.auto()
#     Completed = enum.auto()
#     Errored = enum.auto()


class ChunkRecvStatus(enum.Enum):
    InProgress = enum.auto()
    Completed = enum.auto()
    Errored = enum.auto()


class PalmTreeProtocol:

    def __init__(
          self,
          center_peer,
          session,
          peers_list,
          config: PalmTreeConfig,
    ):
        """
        This is a sans implementation of the gossip protocol.

        Protocol implementation for managing the gossip tree of a peer.
        Commands are sent to a interpreter that does the communication, and responses are handled by the protocol.

        Args:
            center_peer(RemotePeer) : center peer of the session, usually the one who initiated the transfer
            session(PalmTreeSession): session object related to current transfer
            peers_list(list[RemotePeer]): list of remote peer objects participating in transfer
        """
        self.peer_list = peers_list
        self.center_peer = center_peer
        self.session = session
        self.config = config
        self._eager_peers = []
        self._lazy_peers = []
        self._seen = defaultdict(set[RemotePeer])
        self._chunk_statuses = {}
        # keep a journal of peer communication state transitions, where the last entry is the current state
        self.peer_statuses: dict[RemotePeer, list[PeerCommState]] = defaultdict(list)

    def init_tree(self):
        failed = []
        for peer in first_pool_of_peers(self.peer_list, self.config.max_fanout):
            try:
                self.peer_statuses[peer].append(PeerCommState.ActiveLinkRequested)
                yield PalmTreeCommand(PalmTreeOps.SendPassiveMessage, peer)
            except OSError:
                failed.append(peer)
                self.peer_statuses[peer].append(PeerCommState.Errored)

    def active_link_ok(self, peer: RemotePeer):
        self.peer_statuses[peer].append(PeerCommState.ActiveLinkActive)
        self._eager_peers.append(peer)
        # once a link request is accepted, start sending all the chunks we have
        for chunk_id in self._chunk_statuses.copy():
            if self._chunk_statuses[chunk_id] != ChunkRecvStatus.Completed:
                continue
            status = yield PalmTreeCommand(PalmTreeOps.ChunkSend, peer, chunk_id)
            if status == PalmTreeOps.ChunkSendFailed:
                self.peer_statuses[peer].append(PeerCommState.Errored)
                break

    def chunk_active(self, chunk_id: str, peer: RemotePeer):
        self._seen[chunk_id].add(peer)

        # we can receive the same chunk from multiple peers, and discard the losing buffer
        # this is useful when the peer we are already receiving has a slow connection,
        # but that is overkill, can be implemented when some heuristics are involved
        if chunk_id not in self._chunk_statuses or self._chunk_statuses[chunk_id] == ChunkRecvStatus.Errored:
            self._chunk_statuses[chunk_id] = ChunkRecvStatus.InProgress
            status = yield PalmTreeCommand(PalmTreeOps.ChunkRecv, peer, chunk_id)
            if status == PalmTreeOps.ChunkRecvFailed:
                self._chunk_statuses[chunk_id] = ChunkRecvStatus.Errored
                self.peer_statuses[peer].append(PeerCommState.Errored)
                return
            self._chunk_statuses[chunk_id] = ChunkRecvStatus.Completed

            for peer in self._lazy_peers:
                yield PalmTreeCommand(PalmTreeOps.ChunkIHave, peer, chunk_id)

        # we are either receiving or received the chunk
        yield PalmTreeCommand(PalmTreeOps.Downgrade, peer)

    def chunk_recv_failed(self, chunk_id: str, peer: RemotePeer):
        self._chunk_statuses[chunk_id] = ChunkRecvStatus.Errored
        self.peer_statuses[peer].append(PeerCommState.Errored)
        for peer in self._seen[chunk_id]:
            if self.peer_statuses[peer][-1] == PeerCommState.Errored:
                continue
            status = yield PalmTreeCommand(PalmTreeOps.ChunkRecv, peer, chunk_id)
            if status == PalmTreeOps.ChunkRecvFailed:
                self.peer_statuses[peer].append(PeerCommState.Errored)
                continue
            break
        else:
            # If we got here, we have no peers that can send us the chunk, so we contact the center peer
            # TODO: see what else can be done here if center peer is not available
            yield PalmTreeCommand(PalmTreeOps.ChunkRecv, self.center_peer, chunk_id)
