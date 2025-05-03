import asyncio
import ipaddress
import os
import platform
import re
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


async def _run_cmd(*args):
    """Run a shell command asynchronously and return stdout"""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()


async def is_wsl_bridged(_cache=[]) -> tuple[bool | None, str]:
    """Check if system's networking mode is Bridged or not in WSL environment.

    Returns:
        tuple[bool | None, str]:
            None: not in WSL
            False: WSL but not bridged
            True: bridged mode likely
    """

    if _cache:
        return _cache[0]

    if 'wsl' not in platform.release().lower():
        _cache.append((None, "Not running in a WSL environment"))
        return _cache[0]

    try:
        # === STEP 1: Get IP address for eth0 ===
        ip_output = await _run_cmd("ip", "-4", "addr", "show", "eth0")
        ip_line = next((line.strip() for line in ip_output.splitlines() if "inet " in line), None)
        if not ip_line:
            _cache.append((False, "Could not find eth0 IP"))
            return _cache[0]

        wsl_ip = ip_line.split()[1].split('/')[0]
        wsl_ip_obj = ipaddress.ip_address(wsl_ip)

        # === STEP 2: Get default gateway ===
        route_output = await _run_cmd("ip", "route")
        gw_line = next((line for line in route_output.splitlines() if line.startswith("default")), "")
        gw_ip = gw_line.split()[2] if gw_line else None

        ip_likely_bridged = any([
            wsl_ip_obj in ipaddress.ip_network("192.168.0.0/16"),
            wsl_ip_obj in ipaddress.ip_network("10.0.0.0/8"),
            wsl_ip_obj in ipaddress.ip_network("172.16.0.0/12")
        ]) and not str(wsl_ip_obj).startswith("172.26")

        # === STEP 3: Parse .wslconfig ===
        win_home_raw = await _run_cmd("cmd.exe", "/c", "echo", "%USERPROFILE%")
        win_home = win_home_raw.replace("\\", "/").replace("C:", "/mnt/c")
        wslconfig_path = f"{win_home}/.wslconfig"

        config_mode = ""
        if os.path.isfile(wslconfig_path):
            with open(wslconfig_path, 'r') as f:
                content = await asyncio.to_thread(f.read)
                match = re.search(r'(?i)networkingMode\s*=\s*(\w+)', content)
                if match:
                    config_mode = match.group(1).lower()

        config_says_bridged = config_mode in {"bridged", "mirrored"}
        likely_bridged = ip_likely_bridged or config_says_bridged

        notes = f"WSL IP: {wsl_ip}, Gateway: {gw_ip}, .wslconfig mode: {config_mode or 'not set'}"
        _cache.append((likely_bridged, notes))
        return likely_bridged, notes

    except Exception as e:
        _cache.append((False, f"Error: {e}"))
        return False, f"Error: {e}"
