"""Typed UI event contract for the conduit boundary.

These classes describe semantic events that cross the UI boundary.
They do not describe websocket framing, reply bookkeeping, or dispatcher
implementation details. The websocket layer should serialize/deserialize
these events through a codec module.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from src.conduit.ui_events_bases import UICommand, UIError, UINotification, UIPrompt, UIPromptReply, UIResult

JsonMap = dict[str, Any]
JsonList = list[Any]
SearchSource = Literal["kad", "gossip", "list"]


class EventType(enum.StrEnum):
    DATA = "0"
    SIGNAL = "1"


class PeerSummary(TypedDict):
    peer_id: str
    name: str
    ip: str
    online: bool


@dataclass(frozen=True, slots=True)
class TransferUpdate:
    transfer_id: str | int
    peer_id: str
    item_path: str | None = None
    progress: int | float | None = None
    confirmation: bool | None = None
    cancelled: bool = False
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectPeer(UICommand):
    peer_id: str


@dataclass(frozen=True, slots=True)
class RequestUsersSync(UICommand):
    pass


@dataclass(frozen=True, slots=True)
class RequestProfilesSync(UICommand):
    pass


@dataclass(frozen=True, slots=True)
class SetSelectedProfile(UICommand):
    profile: dict


@dataclass(frozen=True, slots=True)
class SearchPeersByName(UICommand):
    query: str


@dataclass(frozen=True, slots=True)
class GossipSearchPeers(UICommand):
    query: str


@dataclass(frozen=True, slots=True)
class RequestPeerList(UICommand):
    pass


@dataclass(frozen=True, slots=True)
class SendText(UICommand):
    peer_id: str
    text: str
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class SendFiles(UICommand):
    peer_id: str
    paths: list[str] = field(default_factory=list)
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class SendDirectory(UICommand):
    peer_id: str
    paths: list[str] = field(default_factory=list)
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class SendBigFile(UICommand):
    peer_id: str
    paths: list[str] = field(default_factory=list)
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class SendFilesToMultiplePeers(UICommand):
    peer_ids: list[str]
    paths: list[str] = field(default_factory=list)
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class SendDirectoryToMultiplePeers(UICommand):
    peer_ids: list[str]
    paths: list[str] = field(default_factory=list)
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class ChooseInterface(UIPromptReply):
    interface_id: str | None


@dataclass(frozen=True, slots=True)
class DecideIncomingTransfer(UIPromptReply):
    peer_id: str
    confirmed: bool
    remember: bool | None = None


@dataclass(frozen=True, slots=True)
class ProvideDiscoveryPeerName(UIPromptReply):
    peer_name: str | None


@dataclass(frozen=True, slots=True)
class ProfilesSnapshot(UIResult):
    profiles: JsonMap
    interfaces: JsonList
    request_id: str | int | None = None


@dataclass(frozen=True, slots=True)
class SearchResults(UIResult):
    peers: list[PeerSummary]
    source: SearchSource
    msg_id: str | int | None = None
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class UsersSnapshot(UIResult):
    peers: list[PeerSummary]
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class MessageReceived(UINotification):
    peer_id: str
    text: str
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class MessageSendFailed(UIError):
    peer_id: str
    message_id: str | int | None = None


@dataclass(frozen=True, slots=True)
class PeerPresenceChanged(UINotification):
    peer: PeerSummary


@dataclass(frozen=True, slots=True)
class PeerConnectionStatus(UINotification):
    peer_id: str
    connected: bool


@dataclass(frozen=True, slots=True)
class TransferStatusChanged(UINotification):
    update: TransferUpdate


@dataclass(frozen=True, slots=True)
class InterfaceChoiceRequested(UIPrompt):
    interfaces: JsonMap
    type: str = EventType.DATA


@dataclass(frozen=True, slots=True)
class DiscoveryPeerNameRequested(UIPrompt):
    reason: str


@dataclass(frozen=True, slots=True)
class IncomingTransferDecisionRequested(UIPrompt):
    peer_id: str
    type: str = EventType.DATA
