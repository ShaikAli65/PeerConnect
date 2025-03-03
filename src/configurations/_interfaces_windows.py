import ctypes
import socket

from src.avails.connect import IPAddress

AF_UNSPEC = 0
GAA_FLAG_INCLUDE_PREFIX = 0x10
ERROR_BUFFER_OVERFLOW = 111
ERROR_SUCCESS = 0
LOOP_BACK_TYPE = 24


def get_interfaces(address_family: socket.AF_INET | socket.AF_INET6):
    if_info = []

    # The basic SOCKADDR structure.
    class SOCKADDR(ctypes.Structure):
        _fields_ = [("sa_family", ctypes.c_ushort), ("sa_data", ctypes.c_char * 14)]

    # Structure for IPv4 addresses.
    class SOCKADDR_IN(ctypes.Structure):
        _fields_ = [
            ("sin_family", ctypes.c_short),
            ("sin_port", ctypes.c_ushort),
            ("sin_addr", ctypes.c_ubyte * 4),
            ("sin_zero", ctypes.c_char * 8),
        ]

    # Structure for an IPv6 address (16 bytes)
    class IN6_ADDR(ctypes.Structure):
        _fields_ = [("Byte", ctypes.c_ubyte * 16)]

    # Structure for IPv6 socket address.
    class SOCKADDR_IN6(ctypes.Structure):
        _fields_ = [
            ("sin6_family", ctypes.c_short),
            ("sin6_port", ctypes.c_ushort),
            ("sin6_flowinfo", ctypes.c_ulong),
            ("sin6_addr", IN6_ADDR),
            ("sin6_scope_id", ctypes.c_ulong),
        ]

    # SOCKET_ADDRESS as used in the Windows API.
    class SOCKET_ADDRESS(ctypes.Structure):
        _fields_ = [
            ("lpSockaddr", ctypes.POINTER(SOCKADDR)),
            ("iSockaddrLength", ctypes.c_int),
        ]

    # Forward declaration for IP_ADAPTER_UNICAST_ADDRESS.
    class IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
        pass

    LP_IP_ADAPTER_UNICAST_ADDRESS = ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)

    IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
        ("Length", ctypes.c_ulong),
        ("Flags", ctypes.c_ulong),
        ("Next", LP_IP_ADAPTER_UNICAST_ADDRESS),
        ("Address", SOCKET_ADDRESS),
    ]

    # Forward declaration for IP_ADAPTER_ADDRESSES.
    class IP_ADAPTER_ADDRESSES(ctypes.Structure):
        pass

    LP_IP_ADAPTER_ADDRESSES = ctypes.POINTER(IP_ADAPTER_ADDRESSES)

    # Note: We only need to define the fields up through FriendlyName and a few more.
    # (The actual structure has many more fields.)
    IP_ADAPTER_ADDRESSES._fields_ = [
        ("Length", ctypes.c_ulong),
        ("IfIndex", ctypes.c_ulong),
        ("Next", LP_IP_ADAPTER_ADDRESSES),
        ("AdapterName", ctypes.c_char_p),
        ("FirstUnicastAddress", LP_IP_ADAPTER_UNICAST_ADDRESS),
        ("FirstAnycastAddress", ctypes.c_void_p),
        ("FirstMulticastAddress", ctypes.c_void_p),
        ("FirstDnsServerAddress", ctypes.c_void_p),
        ("DnsSuffix", ctypes.c_wchar_p),
        ("Description", ctypes.c_wchar_p),
        ("FriendlyName", ctypes.c_wchar_p),
        ("PhysicalAddress", ctypes.c_ubyte * 8),  # MAX_ADAPTER_ADDRESS_LENGTH is 8
        ("PhysicalAddressLength", ctypes.c_ulong),
        ("Flags", ctypes.c_ulong),
        ("Mtu", ctypes.c_ulong),
        ("IfType", ctypes.c_ulong),
        ("OperStatus", ctypes.c_int),
        ("Ipv6IfIndex", ctypes.c_ulong),
        ("ZoneIndices", ctypes.c_ulong * 16),
        # Many more fields follow, but we don't use them.
    ]

    def get_adapters():
        # Load the IP Helper API.
        GetAdaptersAddresses = ctypes.windll.iphlpapi.GetAdaptersAddresses
        GetAdaptersAddresses.argtypes = [
            ctypes.c_ulong,  # Family: AF_UNSPEC to get both IPv4 and IPv6
            ctypes.c_ulong,  # Flags
            ctypes.c_void_p,  # Reserved = NULL
            LP_IP_ADAPTER_ADDRESSES,  # Pointer to adapter addresses
            ctypes.POINTER(ctypes.c_ulong),  # Size of the buffer
        ]

        size = ctypes.c_ulong(15000)  # initial buffer size
        while True:
            buf = ctypes.create_string_buffer(size.value)
            pAddresses = ctypes.cast(buf, LP_IP_ADAPTER_ADDRESSES)
            ret_val = GetAdaptersAddresses(
                AF_UNSPEC, GAA_FLAG_INCLUDE_PREFIX, None, pAddresses, ctypes.byref(size)
            )
            if ret_val == ERROR_SUCCESS:
                break
            elif ret_val == ERROR_BUFFER_OVERFLOW:
                # Buffer too small try again with the new size.
                continue
            else:
                raise ctypes.WinError(ret_val)

        # Build a Python list of adapter structures.
        adapter = pAddresses
        while adapter:
            yield adapter.contents
            adapter = adapter.contents.Next

    for adapter in get_adapters():
        # Use the friendly name if available, otherwise the AdapterName.

        if adapter.IfType == LOOP_BACK_TYPE or adapter.OperStatus != 1:
            continue

        ip = ""
        scope_id = -1

        ua = adapter.FirstUnicastAddress
        while ua:
            # Get the family from the underlying sockaddr.
            sa_family = ua.contents.Address.lpSockaddr.contents.sa_family
            if sa_family == address_family == socket.AF_INET:
                # Cast to IPv4 structure.
                addr_in = ctypes.cast(
                    ua.contents.Address.lpSockaddr, ctypes.POINTER(SOCKADDR_IN)
                ).contents
                # Get the 4-byte IP address.
                ip_addr = bytes(addr_in.sin_addr)
                ip = socket.inet_ntop(socket.AF_INET, ip_addr)

            elif sa_family == address_family == socket.AF_INET6:
                # Cast to IPv6 structure.
                addr_in6 = ctypes.cast(
                    ua.contents.Address.lpSockaddr, ctypes.POINTER(SOCKADDR_IN6)
                ).contents
                # Extract the 16-byte address.
                ip_addr = bytes(bytearray(addr_in6.sin6_addr.Byte))
                ip = socket.inet_ntop(socket.AF_INET6, ip_addr)
                scope_id = addr_in6.sin6_scope_id
            ua = ua.contents.Next
        res = IPAddress(
            ip=ip,
            scope_id=scope_id,
            if_name=adapter.AdapterName,
            friendly_name=adapter.FriendlyName,
        )
        if_info.append(res)
    return if_info
