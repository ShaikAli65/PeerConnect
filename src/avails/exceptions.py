import asyncio
from typing import Any


class AppConnectionError(ConnectionError):
    """Errors raised by the application code explicitly for connection related issues."""


class CannotConnect(AppConnectionError):
    """Cannot connect to provided address or peer"""


class UnknownConnectionType(AppConnectionError):
    """Unknown connection type"""


class TransferIncomplete(Exception):
    """Data Transfer was paused or broken in between"""


class TransferRejected(TransferIncomplete):
    """Data Transfer request was rejected"""


class CancelTransfer(TransferIncomplete):
    """Request to Cancel the transfer"""


class FailedToSend(TransferIncomplete):
    """Failed to Send Something"""
    item: Any
    future: asyncio.Future


class FailedToReceive(TransferIncomplete):
    """Failed to receive completely"""

    def __init__(self, received=0, *args):
        super().__init__(received, *args)
        self.received = received


class InvalidPacket(TypeError):
    """Ill formed Packet"""


class InvalidStateError(Exception):
    """The operation is not allowed in this state."""


class ResourceBusy(Exception):
    """Resource is busy

    Attributes:
        available_after(asyncio.Condition):gets released when resource is freed

    """
    available_after: asyncio.Condition


class RemotePeerNotFound(LookupError):
    """RemotePeer object not found anywhere"""
    peer_id: str


class SearchExhausted(Exception):
    """Search iterator is expired, cannot be iterated, This is different from StopIteration"""
