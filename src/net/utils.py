import asyncio
import socket
import struct
import typing
from socket import AddressFamily, IPPROTO_TCP, IPPROTO_UDP
from typing import Annotated, Awaitable, Union

SHORT_INT = 4
LONG_INT = 8


async def recv_int(get_bytes: typing.Callable[[int], Awaitable[bytes]], type=SHORT_INT):
    """Receives integer from get_bytes function

    awaits on ``get_bytes``, gets bytes based on ``type`` argument
    unpacks it using ``struct.unpack``

    Args:
        get_bytes (Callable[[int], Awaitable[bytes]]): function to receive bytes from
        type: `SHORT_INT` and `LONG_INT`

    Returns:
        int: unpacked integer

    Raises:
        ValueError : on ConnectionResetError or struct.error
    """
    try:
        byted_int = await get_bytes(type)
        integer = struct.unpack('!I' if type == SHORT_INT else '!Q', byted_int)[0]
        return integer
    except struct.error as se:
        raise ValueError(f"unable to unpack integer from: {byted_int}") from se  # noqa
    except ConnectionResetError as ce:
        raise ValueError(f"unable to receive integer") from ce


_AddressFamily = Annotated[AddressFamily, 'v4 or v6 family']
_SockType = Annotated[Union[socket.SOCK_STREAM, socket.SOCK_DGRAM], 'STREAM OR UDP']
_IpProto = Annotated[Union[IPPROTO_TCP, IPPROTO_UDP], "tcp or udp protocol"]
_CannonName = Annotated[str, 'canonical name']
_SockAddr = Annotated[Union[tuple[str, int], tuple[str, int, int, int]], "address tuple[2] if v4 tuple[4] if v6"]


async def get_addr_info(
        host: bytes | str | None,
        port: bytes | str | int | None,
        *,
        family: int = 0,
        type: int = 0,  # noqa
        proto: int = 0,
        flags: int = 0
):
    """Just a convenience for asynchronous name resolving

    Args:
        host: passed into get addr info
        port: passed into get addr info
        family: passed into get addr info
        type: passed into get addr info
        proto: passed into get addr info
        flags: passed into get addr info

    Yields:
        tuple[
            _AddressFamily,
            _SockType,
            _IpProto,
            _CannonName,
            _SockAddr,
        ]
    """

    loop = asyncio.get_running_loop()
    addresses = await loop.getaddrinfo(host, port, family=family, type=type,
                                       proto=proto, flags=flags)

    for family, sock_type, proto, canonname, addr in addresses:
        yield family, sock_type, proto, canonname, addr
