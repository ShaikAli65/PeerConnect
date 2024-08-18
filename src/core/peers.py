from src.avails import PeerDict, RemotePeer
from ..avails import connect

peer_list = PeerDict()
_this_object = RemotePeer()


def get_this_remote_peer():
    return _this_object


def set_current_remote_peer_object(remote_peer):
    global _this_object
    _this_object = remote_peer


def discover():
    ...
