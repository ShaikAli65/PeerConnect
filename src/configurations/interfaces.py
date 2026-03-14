"""Get available network interfaces

Provides a cross compatible way to get system's network interfaces using APIs provided by Operating Systems

Common Usage:
    get_interfaces() -> type: list[net.IPAddress]

"""

import logging
from src.avails import const
from src.net import IPAddress, get_interfaces as _get_interfaces

logger = logging.getLogger(__package__)

_if_info: list | None = None


def reset():
    global _if_info
    logger.info("reloading interfaces...")
    _if_info = _get_interfaces(const.IP_VERSION)


def get_ip_with_ifname(if_name: str):
    for ip in _if_info:
        if str(ip.if_name) == if_name:
            return ip
    raise ValueError(f"No interface found with given name: {if_name=}")


def get_ip_with_ip(ip_addr: str):
    for ip in _if_info:
        if ip.ip == ip_addr:
            return ip
    raise ValueError("No interface with given ip")


def get_interfaces() -> list[IPAddress]:
    if _if_info is None:
        reset()

    return _if_info
