import socket

from ..core import *


class Socket(socket.socket):
    """
    Just an afterthought for any changes in the way we work with socket
    Like connecting to a peer may be changed in future
    """

    def __init__(self, family: socket.AddressFamily | int = -1,
                 _type: socket.SocketKind | int = -1,
                 proto: int = -1,
                 fileno: int | None = None):
        super().__init__(family, _type, proto, fileno)

    def connect(self, address):
        return super().connect(address)

    def bind(self, __address):
        return super().bind(__address)

    def connect_ex(self, __address):
        return super().connect_ex(__address)


def create_connection(address, timeout=socket.getdefaulttimeout(), source_address=None):
    return socket.create_connection(address, timeout, source_address)


def create_server(address,*, family=-1, backlog=-1, reuse_port=False, dual_stack=False):
    return socket.create_server(address, family=family, backlog=backlog, reuse_port=reuse_port, dualstack_ipv6=dual_stack)
