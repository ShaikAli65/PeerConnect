class DispatcherFinalizing(Exception):
    """Operation called when Dispatcher finalizing"""


class WebSocketRegistryReStarted(Exception):
    """WebSocketRegistry already started"""


class InvalidPacket(Exception):
    """Ill formed Packet"""


class UnknownConnectionType(Exception):
    """Unknown connection type"""


class TransferIncomplete(Exception):
    """Data Transfer was paused or broken in between"""
