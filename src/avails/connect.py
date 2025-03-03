import asyncio as _asyncio
import ipaddress
import logging
import socket as _socket

from src.avails import useables
from src.avails._asocket import *  # noqa
from src.avails._conn import *  # noqa
from src.avails._netproto import *  # noqa

_logger = logging.getLogger(__name__)


class IPAddress(NamedTuple):
    """
    Attributes:
        ip: ip address either v4 or v6
        scope_id: interface id if address is v6
        if_name: name of the corresponding interface
        friendly_name: friendly name of the corresponding interface
    """

    ip: str
    scope_id: int
    if_name: str = "N/A"
    friendly_name: str = "N/A"

    def addr_tuple(self, *, port: int, ip=None):
        """A tuple that can be directly passed into socket.bind or socket.connect

        Tuple may be of length 4 based on ip passed in or self.ip

        Args:
            port(int): port that needs to be included in returned tuple
            ip(str): overrides containing ip if provided  # useful when connecting to some ipv6

        Returns:
            tuple[str, int, int, int] | tuple[str,int]
        """

        if ip is None:
            ip = ipaddress.ip_address(self.ip)
        else:
            ip = ipaddress.ip_address(ip)

        if ip.version == 4:
            return str(ip), port

        if ip.version == 6:
            ipaddr = str(ip)
            flow_info = 0
            scope_id = 0 if self.scope_id < 0 else self.scope_id
            return ipaddr, port, flow_info, scope_id


Addr = IPAddress | tuple[str, int] | tuple[str, int, int, int]


def create_connection_sync(
        address, timeout=None
) -> Socket:
    addr_family = _socket.AF_INET if ipaddress.ip_address(address[0]).version == 4 else _socket.AF_INET6
    sock = Socket(addr_family, _socket.SOCK_STREAM)
    sock.settimeout(timeout)

    if const.USING_IP_V6 and len(address) != 4:
        address = const.THIS_IP.addr_tuple(port=address[1], ip=address[0])

    sock.connect(address)
    return sock


async def create_connection_async(address, timeout=None) -> Socket:
    loop = _asyncio.get_running_loop()
    if const.USING_IP_V6 and len(address) != 4:
        address = const.THIS_IP.addr_tuple(port=address[1], ip=address[0])
    sock = await const.PROTOCOL.create_connection_async(loop, address, timeout)
    return sock


CONN_URI = "uri"
REQ_URI = "req_uri"


def connect_to_peer(
        _peer_obj=None, to_which: str = CONN_URI, timeout=None, retries: int = 1
) -> Socket:
    """Creates a basic socket connection to the peer_obj passed in.

    pass `REQ_URI` to connect to req_uri of peer

    :param timeout: initial timeout to start from, in exponential retries
    :param to_which: specifies to what uri should the connection made
    :param _peer_obj: RemotePeer object
    :param retries: if given tries reconnecting with exponential backoff using :func:`useables.get_timeouts`
            uses :param timeout: as initial value

    """

    address = getattr(_peer_obj, to_which)

    if timeout is None:
        return create_connection_sync(address)

    retry_count = 0
    for timeout in useables.get_timeouts(timeout, max_retries=retries):
        try:
            return create_connection_sync(
                address, timeout=timeout
            )
        except OSError:
            retry_count += 1
            if retry_count >= retries:
                raise

    raise OSError


@useables.awaitable(connect_to_peer)
async def connect_to_peer(
        _peer_obj=None, to_which=CONN_URI, timeout=None, retries: int = 1
) -> Socket:
    """
    Creates a basic socket connection to the peer_obj passed in.
    pass `const.REQ_URI_CONNECT` to connect to req_uri of peer
    *args will be passed into socket.setsockopt
    :param timeout: initial timeout to start from, in exponential retries
    :param to_which: specifies to what uri should the connection made
    :param _peer_obj: RemotePeer object
    :param retries: if given tries reconnecting with exponential backoff using :func:`useables.get_timeouts`
    :param timeout: uses as initial value
    :returns: connected socket if successful
    :raises: OSError
    """

    address = getattr(_peer_obj, to_which)

    retry_count = 0

    if timeout is None:
        return await create_connection_async(address)

    for timeout in useables.get_timeouts(timeout, max_retries=retries):
        try:
            return await create_connection_async(address, timeout)
        except OSError:
            retry_count += 1
            if retry_count >= retries:
                raise
    raise OSError


def is_socket_connected(sock: Socket):
    blocking = sock.getblocking()
    keep_alive = sock.getsockopt(_socket.SOL_SOCKET, _socket.SO_KEEPALIVE)

    try:
        sock.setblocking(False)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_KEEPALIVE, 1)
        sock.getpeername()
        data = sock.recv(1, _socket.MSG_PEEK)
        return data != b""
    except BlockingIOError:
        return True
    except OSError:
        return False
    finally:
        try:
            sock.setblocking(blocking)
            sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_KEEPALIVE, keep_alive)
        except OSError:
            return False


def get_free_port(ip=None) -> int:
    """Gets a free port from the system."""
    ip = const.THIS_IP.addr_tuple(port=0, ip=ip)
    with _socket.socket(const.IP_VERSION, _socket.SOCK_STREAM) as s:
        s.bind(ip)
        return s.getsockname()[1]  # Port is empty


def ipv4_multicast_socket_helper(
        sock, local_addr, multicast_addr, *, loop_back=0, ttl=1, add_membership=True
):
    sock.setsockopt(_socket.IPPROTO_IP, _socket.IP_MULTICAST_TTL, ttl)
    sock.setsockopt(_socket.IPPROTO_IP, _socket.IP_MULTICAST_LOOP, loop_back)
    if add_membership:
        group = _socket.inet_aton(f"{multicast_addr[0]}")

        if not const.IS_WINDOWS:
            mreq = struct.pack("4sl", group, _socket.INADDR_ANY)
        else:
            mreq = struct.pack("4s4s", group, _socket.inet_aton(str(local_addr[0])))

        sock.setsockopt(_socket.IPPROTO_IP, _socket.IP_ADD_MEMBERSHIP, mreq)
    sock_options = {
        "membership": add_membership,
        "loop_back": loop_back,
        "ttl": ttl,
    }
    _logger.debug(f"options for multicast {sock_options}, {sock}")


def ipv6_multicast_socket_helper(
        sock, multicast_addr, *, loop_back=0, add_membership=True, hops=1
):
    sock.setsockopt(_socket.IPPROTO_IPV6, _socket.IPV6_MULTICAST_LOOP, loop_back)
    sock.setsockopt(_socket.IPPROTO_IPV6, _socket.IPV6_MULTICAST_HOPS, hops)

    ip, port, _flow, interface_id = sock.getsockname()
    sock.setsockopt(_socket.IPPROTO_IPV6, _socket.IPV6_MULTICAST_IF, interface_id)

    if add_membership:
        group = _socket.inet_pton(_socket.AF_INET6, f"{multicast_addr[0]}")
        mreq = group + struct.pack("@I", interface_id)
        sock.setsockopt(_socket.IPPROTO_IPV6, _socket.IPV6_JOIN_GROUP, mreq)

    sock_options = {
        "ip": ip,
        "port": port,
        "multicast addr": multicast_addr,
        "interface": interface_id,
        "membership": add_membership,
        "loop_back": loop_back,
        "hops": hops,
    }
    _logger.debug(f"options for multicast:{sock_options}")
