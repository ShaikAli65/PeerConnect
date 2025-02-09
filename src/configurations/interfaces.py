from src.avails import const

if const.IS_WINDOWS:
    from ._interfaces_windows import get_interfaces as _get_interfaces
else:
    from ._interfaces_linux import get_interfaces as _get_interfaces

_if_info: list | None = None


def reset():
    global _if_info
    _if_info = _get_interfaces(const.IP_VERSION)


def get_ip_with_ifname(if_name: str):
    for ip in _if_info:
        if ip.if_name == if_name:
            return ip
    raise ValueError("No interface found with given name")


def get_ip_with_ip(ip_addr: str):
    for ip in _if_info:
        if ip.ip == ip_addr:
            return ip
    raise ValueError("No interface with given ip")


def get_interfaces():
    if _if_info is None:
        reset()

    return _if_info
