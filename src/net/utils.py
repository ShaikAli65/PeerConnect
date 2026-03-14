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


def _is_wsl_environment() -> bool:
    if os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"):
        return True

    for proc_file in ("/proc/sys/kernel/osrelease", "/proc/version"):
        try:
            with open(proc_file, "r") as f:
                if "microsoft" in f.read().lower():
                    return True
        except OSError:
            continue

    return "wsl" in platform.release().lower()


def _find_default_route(route_output: str) -> tuple[str | None, str | None]:
    for line in route_output.splitlines():
        if not line.startswith("default"):
            continue

        tokens = line.split()
        gateway = None
        interface = None

        if "via" in tokens:
            via_idx = tokens.index("via")
            if via_idx + 1 < len(tokens):
                gateway = tokens[via_idx + 1]

        if "dev" in tokens:
            dev_idx = tokens.index("dev")
            if dev_idx + 1 < len(tokens):
                interface = tokens[dev_idx + 1]

        return interface, gateway

    return None, None


def _extract_ipv4_from_addr(ip_output: str) -> tuple[str | None, int | None]:
    for line in ip_output.splitlines():
        if "inet " not in line:
            continue

        cidr = line.strip().split()[1]
        host, prefix = cidr.split("/", 1)
        return host, int(prefix)

    return None, None


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

    if not _is_wsl_environment():
        _cache.append((None, "Not running in a WSL environment"))
        return _cache[0]

    try:
        # Use the interface attached to the default route instead of assuming eth0.
        route_output = await _run_cmd("ip", "route")
        iface, gw_ip = _find_default_route(route_output)
        if not iface:
            _cache.append((False, "Could not determine default route interface"))
            return _cache[0]

        ip_output = await _run_cmd("ip", "-4", "addr", "show", "dev", iface)
        wsl_ip, prefix_len = _extract_ipv4_from_addr(ip_output)
        if not wsl_ip or prefix_len is None:
            _cache.append((False, f"Could not find IPv4 address for {iface}"))
            return _cache[0]

        wsl_ip_obj = ipaddress.ip_address(wsl_ip)

        # Prefer subnet-based inference over broad RFC1918 checks. Bridged/mirrored
        # setups usually place the guest and default gateway on the same LAN subnet.
        ip_likely_bridged = False
        if gw_ip:
            try:
                gateway_obj = ipaddress.ip_address(gw_ip)
                link_net = ipaddress.ip_network(f"{wsl_ip}/{prefix_len}", strict=False)
                ip_likely_bridged = gateway_obj in link_net and gateway_obj != wsl_ip_obj
            except ValueError:
                ip_likely_bridged = False

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

        notes = (
            f"WSL iface: {iface}, IP: {wsl_ip}/{prefix_len}, "
            f"Gateway: {gw_ip}, .wslconfig mode: {config_mode or 'not set'}"
        )
        _cache.append((likely_bridged, notes))
        return likely_bridged, notes

    except Exception as e:
        _cache.append((False, f"Error: {e}"))
        return False, f"Error: {e}"
