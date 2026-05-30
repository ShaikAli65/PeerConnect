import asyncio
import logging
from contextlib import asynccontextmanager

from avails import WireData
from avails.exceptions import InvalidPacket
from net import WireIO
from src import net
from src.transfers import HEADERS
from .protocol import MessageProtocol

logger = logging.getLogger(__package__)


class MessageTransport:
    """
    Handles the transportation of messages over a network by interfacing with a given protocol.

    It ensures that data is received and sent across a connection while adhering to a specified protocol. It can
    handle message receipts, malformed packets, and re-establishment of lost connections. It operates
    asynchronously to support non-blocking communication using `net.MessageSocket`.

    Note:
        Does not handle connection establishment or disconnection or ownership of the connection.
        Connection
    Attributes:
        protocol (MessageProtocol): The protocol instance that manages message semantics and callbacks.
        connection (net.Connection): The current network connection used for communication.

    """
    def __init__(self, protocol: MessageProtocol):
        self._msg_socket = net.MessageSocket(should_prune_buffer_on_full=False, logger=logger)
        self.protocol = protocol
        self._receiver_task = None
        self.connection = None

    def connection_made(self, connection: net.Connection):
        self._msg_socket.update_transport(connection)
        self.connection = connection

    async def start_receiving(self):
        while True:
            # TODO: what if connection is lost? and it is established again? and we lost the update
            # cause we didn't call wait_for before the connection was re-established
            async with self._msg_socket.connection_restablished:
                logger.debug(f"#< waiting for connection to be re-established")
                await self._msg_socket.connection_restablished.wait()

            logger.debug("#< connection re-established, starting receiving")
            try:
                await self._recv_loop()
            except OSError as exc:
                logger.info("!< transport closed")
                await self.protocol.connection_lost(exc)

    async def _recv_loop(self):
        while True:
            try:
                wire_data = await WireIO.recv_msg(self.connection)
                logger.debug(f"#< new msg {wire_data}")
            except InvalidPacket:
                logger.info(f"!< malformed packet", exc_info=True)
                continue

            if wire_data.match_header(HEADERS.MSG_READ_RECEIPT):
                await self.protocol.message_receipt_received(
                    wire_data.body["receipt"],
                    wire_data.peer_id
                )
                continue

            await self.protocol.message_received(wire_data.body, wire_data.peer_id)

    async def send_data(self, data: WireData):
        await self._msg_socket(bytes(data))

    @asynccontextmanager
    async def context_manager(self):
        try:
            self._receiver_task = asyncio.create_task(self.start_receiving())
            async with self._msg_socket.context_manager():
                yield self
        finally:
            self._receiver_task.cancel()
