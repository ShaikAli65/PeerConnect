"""App events bus.

All the application events are published through this bus.
Interested parties can subscribe to events and receive them.
"""

import asyncio
import logging
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from src.avails import RemotePeer
from src.avails.bases import AppEventBase

_logger = logging.getLogger(__name__)

__all__ = (
    "PeerStatusUpdate",
    "TransferStarted",
    "TransferProgressUpdated",
    "TransferCompleted",
    "TransferIncomplete",
    "TransferConfirmation",
    "ConnectionArrived",
    "MessageReceived",
    "AppEventsBus",
    "create_app_events_bus",
)


@dataclass(frozen=True, slots=True)
class PeerStatusUpdate(AppEventBase):
    remote_peer: "RemotePeer"


@dataclass(frozen=True, slots=True)
class TransferStarted(AppEventBase):
    transfer_id: str
    peer_id: str
    kind: str | None = None


@dataclass(frozen=True, slots=True)
class TransferProgressUpdated(AppEventBase):
    transfer_id: str
    peer_id: str
    item_path: str | None
    progress: int | float


@dataclass(frozen=True, slots=True)
class TransferCompleted(AppEventBase):
    transfer_id: str
    peer_id: str


@dataclass(frozen=True, slots=True)
class TransferIncomplete(AppEventBase):
    transfer_id: str
    peer_id: str
    item_path: str | None
    progress: int | float | None
    error: str | None


@dataclass(frozen=True, slots=True)
class TransferConfirmation(AppEventBase):
    transfer_id: str
    peer_id: str
    confirmed: bool


@dataclass(frozen=True, slots=True)
class ConnectionArrived(AppEventBase):
    peer_id: str
    connection_info: Any


@dataclass(frozen=True, slots=True)
class MessageReceived(AppEventBase):
    msg: str | None
    peer_id: str
    msg_id: str

#
# @dataclass(frozen=True, slots=True)
# class ConnectionLost(AppEventBase):
#     peer_id: str


class AppEventsBus:
    def __init__(self) -> None:
        self._subs: dict[type[object], set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, event: type[AppEventBase], *, queue: asyncio.Queue[AppEventBase] | None = None,
                  maxsize: int = 0) -> asyncio.Queue:
        """ Subscribe to an event

        You can optionally provide a queue to receive events, this is helpful if you want to receive
        different types of events in the same queue.

        A queue is created if not provided with `maxsize` as the buffer size.

        `None` will be put in the queue during shutdown
        Args:
            event: event class
            queue: queue to receive events
            maxsize: max size of the queue if queue is not provided

        Returns:
            asyncio.Queue: queue to receive events
        """
        _logger.debug("Subscribing to %s", event, stacklevel=2)
        q = queue or asyncio.Queue(maxsize=maxsize)
        self._subs[event].add(q)
        return q

    def unsubscribe(self, event: type[AppEventBase], q: asyncio.Queue) -> None:
        """ Unsubscribe from an event."""
        self._subs[event].discard(q)
        _logger.debug("Unsubscribed from %s", event, stacklevel=2)

    def publish(self, event) -> None:
        """ Publish an event to all subscribers."""
        _logger.debug("Publishing %s", event, stacklevel=2)
        for q in tuple(self._subs[type(event)]):
            with suppress(asyncio.QueueFull):
                q.put_nowait(event)


def create_app_events_bus() -> AppEventsBus:
    return AppEventsBus()
