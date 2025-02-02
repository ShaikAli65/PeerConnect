import ctypes
import socket
import struct
from collections import namedtuple
from typing import Literal

from src.avails import constants


AF_INET = socket.AF_INET
AF_INET6 = socket.AF_INET6
IFF_LOOPBACK = 0x8
IPAddress = namedtuple("IPAddress", ["ip", "scope_id", "if_name"])


def __get_interfaces(
    address_falmily: Literal[AF_INET, AF_INET6], __result=[]
) -> list[IPAddress]:
    if __result:
        return __result[0]

    # Load the C library (adjust the name if needed on your system)
    libc = ctypes.CDLL("libc.so.6")

    # Define the basic sockaddr structure
    class sockaddr(ctypes.Structure):
        _fields_ = [("sa_family", ctypes.c_ushort), ("sa_data", ctypes.c_char * 14)]

    # Define sockaddr_in for IPv4 addresses
    class sockaddr_in(ctypes.Structure):
        _fields_ = [
            ("sin_family", ctypes.c_short),
            ("sin_port", ctypes.c_ushort),
            ("sin_addr", ctypes.c_uint32),  # in_addr (IPv4 address)
            ("sin_zero", ctypes.c_char * 8),
        ]

    # Define in6_addr structure for IPv6 addresses
    class in6_addr(ctypes.Structure):
        _fields_ = [("s6_addr", ctypes.c_ubyte * 16)]

    # Define sockaddr_in6 for IPv6 addresses
    class sockaddr_in6(ctypes.Structure):
        _fields_ = [
            ("sin6_family", ctypes.c_short),
            ("sin6_port", ctypes.c_ushort),
            ("sin6_flowinfo", ctypes.c_uint32),
            ("sin6_addr", in6_addr),
            ("sin6_scope_id", ctypes.c_uint32),
        ]

    # Forward declaration for ifaddrs since it is self-referential
    class ifaddrs(ctypes.Structure):
        pass

    ifaddrs._fields_ = [
        ("ifa_next", ctypes.POINTER(ifaddrs)),
        ("ifa_name", ctypes.c_char_p),
        ("ifa_flags", ctypes.c_uint),
        ("ifa_addr", ctypes.POINTER(sockaddr)),
        ("ifa_netmask", ctypes.POINTER(sockaddr)),
        (
            "ifa_ifu",
            ctypes.POINTER(sockaddr),
        ),  # This field can hold the broadcast or destination address
        ("ifa_data", ctypes.c_void_p),
    ]

    # Set up function prototypes for getifaddrs and freeifaddrs
    getifaddrs = libc.getifaddrs
    getifaddrs.argtypes = [ctypes.POINTER(ctypes.POINTER(ifaddrs))]
    getifaddrs.restype = ctypes.c_int

    freeifaddrs = libc.freeifaddrs
    freeifaddrs.argtypes = [ctypes.POINTER(ifaddrs)]

    """Retrieve IP addresses bound to each network interface, including scope IDs for IPv6."""
    ifap = ctypes.POINTER(ifaddrs)()
    if getifaddrs(ctypes.byref(ifap)) != 0:
        raise OSError("getifaddrs() call failed")

    interfaces = []
    p = ifap
    while p:
        iface = p.contents
        if iface.ifa_addr:
            family = iface.ifa_addr.contents.sa_family
            iface_name = iface.ifa_name.decode("utf-8") if iface.ifa_name else None

            if not (family == AF_INET or family == AF_INET6) or bool(
                iface.ifa_flags & IFF_LOOPBACK
            ):
                p = iface.ifa_next
                continue

            if family == address_falmily == AF_INET:
                addr_in = ctypes.cast(
                    iface.ifa_addr, ctypes.POINTER(sockaddr_in)
                ).contents
                ip_addr = socket.inet_ntoa(struct.pack("I", addr_in.sin_addr))

                # -1 is just to fill the field but ipv4 donot have any scope_ids
                scope_id = -1
            elif family == address_falmily == AF_INET6:  # for ip v6
                addr_in = ctypes.cast(
                    iface.ifa_addr, ctypes.POINTER(sockaddr_in6)
                ).contents

                ip_addr = socket.inet_ntop(
                    AF_INET6, bytes(bytearray(addr_in.sin6_addr.s6_addr))
                )

                scope_id = addr_in.sin6_scope_id
            else:
                p = iface.ifa_next
                continue
            interfaces.append(
                IPAddress(ip=ip_addr, scope_id=scope_id, if_name=iface_name)
            )
        p = iface.ifa_next

    freeifaddrs(ifap)
    return interfaces


def get_ip_with_ifname(if_name: str):
    for ip in __get_interfaces(constants.IP_VERSION):
        if ip.if_name == if_name:
            return ip
    raise ValueError("No interface found with given name")


def get_ip_with_ip(ip_addr: str):
    for ip in __get_interfaces(constants.IP_VERSION):
        if ip.ip == ip_addr:
            return ip
    raise ValueError("No interface with given ip")
