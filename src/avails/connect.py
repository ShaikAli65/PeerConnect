import random
import socket as soc

import select
import socket
from typing import Optional

import src.avails.constants as const


class Socket(socket.socket):
    """
    Just an afterthought for any changes in the way we work with socket
    Like connecting to a peer may be changed in future
    """

    def accept(self):
        fd, addr = self._accept()
        # Cast the new socket to the custom Socket class
        custom_socket = self.__class__(self.family,self.type,self.proto,fileno=fd)
        if socket.getdefaulttimeout() is None and self.gettimeout():
            custom_socket.setblocking(True)
        return custom_socket, addr


def wrap_sock(sock):
    custom_sock = Socket(sock.family,sock.type,sock.proto,fileno=sock.fileno())
    # sock.detach()
    # sock.close()
    return custom_sock


def create_connection(address, timeout=socket.getdefaulttimeout(), source_address=None) -> Socket:
    # return wrap_sock(socket.create_connection(address, timeout, source_address))
    address_info = socket.getaddrinfo(address[0], address[1], proto=const.PROTOCOL)[0]
    address = address_info[4][:2]
    sock_family = address_info[0]
    sock_type = address_info[1]
    sock = Socket(family=sock_family,type=sock_type)
    if source_address:
        sock.bind(source_address)
    sock.settimeout(timeout)
    sock.connect(address)
    return sock


def create_server(address,*, family=-1, backlog=-1, dual_stack=False) -> Socket:
    # sock = socket.create_server(address, family=family, backlog=backlog, reuse_port=reuse_port, dualstack_ipv6=dual_stack)
    address_info = socket.getaddrinfo(address[0], address[1], family=family, proto=const.PROTOCOL)[0]
    address = address_info[4][:2]
    sock_family = address_info[0]
    sock_type = address_info[1]
    sock = Socket(family=sock_family, type=sock_type)
    if dual_stack:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(address)
    sock.listen(backlog) if backlog else sock.listen()
    return sock


BASIC_URI_CONNECT = 13
REQ_URI_CONNECT = 12


def connect_to_peer(_peer_obj=None, peer_id=None, to_which: int = BASIC_URI_CONNECT, timeout=None):
    """
    Creates a basic socket connection to peer id passed in, or to the peer_obj passed in.
    peer_obj is given higher priority
    The another argument :param to_which: specifies to what uri should the connection made,
    pass :param const.REQ_URI_CONNECT: to connect to req_uri of peer
    :param timeout:
    :param _peer_obj:
    :param peer_id:
    :param to_which:
    :return:
    """
    peer_obj = _peer_obj or const.LIST_OF_PEERS.get_peer(peer_id)
    addr = peer_obj.req_uri if to_which == REQ_URI_CONNECT else peer_obj.uri
    return create_connection(addr,timeout)


def read_sock(sock, actuator, data_len, timeout=10) -> Optional[bytes]:
    reads, _, _ = select.select([sock, actuator],[],[], timeout)
    if sock in reads:
        return sock.recv(data_len)
    return None


def is_socket_connected(sock:Socket):
    try:
        sock.getpeername()
        sock.setblocking(False)
        data = sock.recv(1, socket.MSG_PEEK)
        return False if data == b'' else True
    except BlockingIOError:
        return True
    except (ConnectionResetError, ConnectionError, ConnectionAbortedError, OSError):
        return False
    finally:
        try:
            sock.setblocking(True)
        except OSError:
            return False


def get_free_port() -> int:
    """Gets a free port from the system."""
    random_port = random.randint(1024, 65535)
    while not is_port_empty(random_port):
        random_port = random.randint(1024, 65535)
    return random_port


def is_port_empty(port):
    try:
        # print(THIS_IP,IP_VERSION)
        with soc.socket(const.IP_VERSION, soc.SOCK_STREAM) as s:
            s.bind((const.THIS_IP, port))
            return True
    except socket.gaierror:
        print("ERROR IN SETTING UP NETWORK ")
        exit(1)
    except (OSError, socket.error):
        return False
