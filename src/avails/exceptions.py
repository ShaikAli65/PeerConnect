import asyncio
from typing import Any


class DispatcherFinalizing(Exception):
    """Dispatcher is finalizing no longer working"""


class WebSocketRegistryReStarted(Exception):
    """WebSocketRegistry already started"""


class InvalidPacket(TypeError):
    """Ill formed Packet"""


class UnknownConnectionType(Exception):
    """Unknown connection type"""


class TransferIncomplete(Exception):
    """Data Transfer was paused or broken in between"""


class TransferRejected(Exception):
    """Data Transfer request was rejected"""


class CancelTransfer(Exception):
    """Request to Cancel the transfer"""


class InvalidStateError(Exception):
    """The operation is not allowed in this state."""


class CannotConnect(OSError):
    """Cannot connect to provided address or peer"""


class ResourceBusy(Exception):
    """Resource is Busy

    Attributes:
        available_after(asyncio.Condition):gets released when resource is freed

    """
    available_after: asyncio.Condition


class RemotePeerNotFound(Exception):
    """RemotePeer object not found anywhere"""
    peer_id: str


class SearchExhausted(Exception):
    """Search iterator is expired, cannot be iterated, This is different from StopIteration"""


class FailedToSend(TransferIncomplete):
    """Failed to Send Something"""
    item: Any


class FailedToReceive(TransferIncomplete):
    """Failed to receive completely"""

    def __init__(self, received=0, *args):
        super().__init__(received, *args)
        self.received = received
