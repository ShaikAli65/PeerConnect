class DispatcherFinalizing(Exception):
    """Dispatcher is finalizing no longer working"""


class WebSocketRegistryReStarted(Exception):
    """WebSocketRegistry already started"""


class InvalidPacket(Exception):
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
