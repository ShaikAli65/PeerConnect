class DispatcherFinalizing(Exception):
    pass


class WebSocketRegistryReStarted(Exception):
    """WebSocketRegistry already started"""


class InvalidPacket(Exception):
    """Ill formed Packet"""
