import struct
from asyncio import BaseTransport
from typing import Any, Awaitable, Coroutine, Optional

import umsgpack

from src.avails import WireData, const as _const
from src.avails.exceptions import InvalidPacket
from .connect import MsgConnection, Receiver, Socket as _Socket, is_socket_connected
from .utils import recv_int
from .waiters import Actuator, wait_for_sock_read

_controller = Actuator()


class WireIO:
    @staticmethod
    async def send_async(sock: _Socket, data: bytes):
        data_size = struct.pack("!I", len(data))
        return await sock.asendall(data_size + data)

    @staticmethod
    def send_msg(connection, msg) -> Awaitable[None]:
        """

        Args:
            connection(Connection): connection object
            msg(WireData):data to send

        """
        messaged = MsgConnection(connection)
        return messaged.send(msg)

    @staticmethod
    def recv_msg(connection) -> Coroutine[Any, Any, WireData]:
        """
        Args:
            connection(Connection): connection object
        Returns:
            WireData: on successful receive
        """
        msg_con = MsgConnection(connection)
        return msg_con.recv()

    @staticmethod
    def send(sock: _Socket, data: bytes):
        data_size = struct.pack("!I", len(data))
        return sock.sendall(data_size + data)

    @staticmethod
    def send_datagram(sock: _Socket | BaseTransport, address, data: bytes):
        if len(data) > _const.MAX_DATAGRAM_SEND_SIZE:
            raise ValueError(
                f"maximum send datagram size is {_const.MAX_DATAGRAM_SEND_SIZE} "
                f"got a packet of size {len(data)} + 4bytes size"
            )

        data_size = struct.pack("!I", len(data))
        return sock.sendto(data_size + data, address)

    @staticmethod
    async def receive_async(sock: _Socket):
        try:
            receiver = Receiver(sock)
            data_size = await recv_int(receiver)
            data = await receiver(data_size)
            return data
        except ValueError:
            if not is_socket_connected(sock):
                raise OSError("connection error")
            raise

    @staticmethod
    def receive(sock: _Socket, timeout=None, controller=_controller):
        b = sock.getblocking()
        length_buf = bytearray()
        while len(length_buf) < 4:
            try:
                data = sock.recv(4 - len(length_buf))
                if data == b"":  # If socket connection is closed prematurely
                    sock.setblocking(b)
                    raise ConnectionError("got empty bytes in a stream socket")
                length_buf += data
            except BlockingIOError:
                wait_for_sock_read(sock, controller, timeout)
        data_length = struct.unpack("!I", length_buf)[0]

        received_data = bytearray()
        while len(received_data) < data_length:
            try:
                chunk = sock.recv(data_length - len(received_data))
                if chunk == b"":  # Again, handle premature disconnection
                    raise ConnectionError("connection closed during data reception")
                received_data += chunk
            except BlockingIOError:
                wait_for_sock_read(sock, controller, timeout)
        sock.setblocking(b)
        return received_data

    @staticmethod
    def recv_datagram(sock: _Socket):
        data, addr = sock.recvfrom(_const.MAX_DATAGRAM_RECV_SIZE)
        return WireIO.load_datagram(data), addr

    @staticmethod
    def load_datagram(data_payload) -> bytes:
        data_size = struct.unpack("!I", data_payload[:4])[0]
        return data_payload[4: data_size + 4]

    @staticmethod
    async def recv_datagram_async(sock: _Socket) -> tuple[bytes, tuple[str, int]]:
        data, addr = await sock.arecvfrom(_const.MAX_DATAGRAM_RECV_SIZE)
        return WireIO.load_datagram(data), addr


def unpack_datagram(data_payload) -> Optional[WireData]:
    """Utility function to unpack raw datagram

        from `datagram_received` callback from asyncio' s DatagramProtocol
        or any other datagram transferred using wire protocol
        Unpack the raw data received using peer-connect' s wire protocol
        into WireData and handle exceptions

    Args:
        data_payload(bytes) : byte string to unpack

    Raises:
        InvalidPacket if unpacking failed
    """
    try:
        data = WireIO.load_datagram(data_payload)
        loaded = WireData.load_from(data)
        return loaded
    except umsgpack.UnpackException as ue:
        raise InvalidPacket("Ill-formed data: %s. Error: %s" % (data_payload, ue)) from ue
    except TypeError as tp:
        raise InvalidPacket("Type error, possibly ill-formed data: %s. Error: %s" % (data_payload, tp)) from tp
    except struct.error as se:
        raise InvalidPacket("struct error, possibly ill-formed data: %s. Error: %s" % (data_payload, se)) from se
