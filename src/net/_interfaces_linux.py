import ctypes
import socket
import struct

from src.avails import const
from src.net import IPAddress
from ._interfaces_windows import INCLUDE_LOOP_BACK

IFF_LOOPBACK = 0x8
IFF_UP = 0x1  # Interface is up.
IFF_RUNNING = 0x40


def get_interfaces(
    address_family: socket.AF_INET | socket.AF_INET6,
) -> list[IPAddress]:
    try:
        libc = ctypes.CDLL("libc.so.6")
    except OSError:
        libc = ctypes.CDLL("libc.dylib")  # For macOS

    # Define sockaddr structure
    class sockaddr(ctypes.Structure):
        if const.IS_DARWIN:
            _fields_ = [
                ("sa_len", ctypes.c_uint8),
                ("sa_family", ctypes.c_uint8),
                ("sa_data", ctypes.c_char * 14),
            ]
        else:
            _fields_ = [
                ("sa_family", ctypes.c_ushort),
                ("sa_data", ctypes.c_char * 14),
            ]

    # Define sockaddr_in for IPv4
    class sockaddr_in(ctypes.Structure):
        if const.IS_DARWIN:
            _fields_ = [
                ("sin_len", ctypes.c_uint8),
                ("sin_family", ctypes.c_uint8),
                ("sin_port", ctypes.c_ushort),
                ("sin_addr", ctypes.c_uint32),
                ("sin_zero", ctypes.c_char * 8),
            ]
        else:
            _fields_ = [
                ("sin_family", ctypes.c_ushort),
                ("sin_port", ctypes.c_ushort),
                ("sin_addr", ctypes.c_uint32),
                ("sin_zero", ctypes.c_char * 8),
            ]

    # Define in6_addr structure
    class in6_addr(ctypes.Structure):
        _fields_ = [("s6_addr", ctypes.c_ubyte * 16)]

    # Define sockaddr_in6 for IPv6
    class sockaddr_in6(ctypes.Structure):
        if const.IS_DARWIN:
            _fields_ = [
                ("sin6_len", ctypes.c_uint8),
                ("sin6_family", ctypes.c_uint8),
                ("sin6_port", ctypes.c_ushort),
                ("sin6_flowinfo", ctypes.c_uint32),
                ("sin6_addr", in6_addr),
                ("sin6_scope_id", ctypes.c_uint32),
            ]
        else:
            _fields_ = [
                ("sin6_family", ctypes.c_ushort),
                ("sin6_port", ctypes.c_ushort),
                ("sin6_flowinfo", ctypes.c_uint32),
                ("sin6_addr", in6_addr),
                ("sin6_scope_id", ctypes.c_uint32),
            ]

    # Forward declaration for ifaddrs
    class ifaddrs(ctypes.Structure):
        pass

    ifaddrs._fields_ = [
        ("ifa_next", ctypes.POINTER(ifaddrs)),
        ("ifa_name", ctypes.c_char_p),
        ("ifa_flags", ctypes.c_uint),
        ("ifa_addr", ctypes.POINTER(sockaddr)),
        ("ifa_netmask", ctypes.POINTER(sockaddr)),
        ("ifa_ifu", ctypes.POINTER(sockaddr)),
        ("ifa_data", ctypes.c_void_p),
    ]

    getifaddrs = libc.getifaddrs
    getifaddrs.argtypes = [ctypes.POINTER(ctypes.POINTER(ifaddrs))]
    getifaddrs.restype = ctypes.c_int

    freeifaddrs = libc.freeifaddrs
    freeifaddrs.argtypes = [ctypes.POINTER(ifaddrs)]

    ifap = ctypes.POINTER(ifaddrs)()
    if getifaddrs(ctypes.byref(ifap)) != 0:
        raise OSError("getifaddrs() call failed")

    interfaces = []
    p = ifap
    while p:
        iface = p.contents
        flags = iface.ifa_flags
        if iface.ifa_addr:
            family = iface.ifa_addr.contents.sa_family
            iface_name = iface.ifa_name.decode("utf-8") if iface.ifa_name else None
            if (
                not (family == socket.AF_INET or family == socket.AF_INET6)
                  or (INCLUDE_LOOP_BACK or bool(flags & IFF_LOOPBACK))
                or not bool(flags & IFF_RUNNING)
            ):
                p = iface.ifa_next
                continue

            if family == address_family == socket.AF_INET:
                addr_in = ctypes.cast(
                    iface.ifa_addr, ctypes.POINTER(sockaddr_in)
                ).contents
                ip_addr = socket.inet_ntoa(struct.pack("I", addr_in.sin_addr))
                scope_id = -1
            elif family == address_family == socket.AF_INET6:
                addr_in = ctypes.cast(
                    iface.ifa_addr, ctypes.POINTER(sockaddr_in6)
                ).contents
                ip_addr = socket.inet_ntop(
                    socket.AF_INET6, bytes(bytearray(addr_in.sin6_addr.s6_addr))
                )
                scope_id = addr_in.sin6_scope_id
            else:
                p = iface.ifa_next
                continue

            res = IPAddress(
                ip=ip_addr,
                scope_id=scope_id,
                if_name=iface_name,
                friendly_name=iface_name,
            )
            interfaces.append(res)

        p = iface.ifa_next

    freeifaddrs(ifap)
    return interfaces
