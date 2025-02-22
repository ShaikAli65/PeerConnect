import asyncio
import logging
import socket
import traceback
from contextlib import AsyncExitStack, aclosing, asynccontextmanager
from pathlib import Path

from src.avails import OTMInformResponse, OTMSession, RemotePeer, TransfersBookKeeper, Wire, WireData, connect, \
    const, get_dialog_handler
from src.avails.events import ConnectionEvent
from src.avails.exceptions import TransferIncomplete, TransferRejected
from src.conduit import webpage
from src.core import peers
from src.core.connector import Connector
from src.core.public import Dock, get_this_remote_peer
from src.transfers import HEADERS, TransferState, files, otm
from src.transfers.status import StatusMixIn

transfers_book = TransfersBookKeeper()

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def send_files_to_peer(peer_id, selected_files):
    """Sends provided files to peer with ``peer_id``
    Gets peer information from peers module

    Args:
        peer_id(str): id of peer to send file to
        selected_files(list[str | Path]): list of file paths

    Yields:
        files.Sender object
    """

    if file_sender_handle := transfers_book.check_running(peer_id):
        # if any transfer is running just attach FileItems to that transfer
        file_sender_handle.attach_files(selected_files)
        return

    file_sender, status_updater = await _send_setup(peer_id, selected_files)
    yield_decision = status_updater.should_yield

    try:
        async with _sender_helper(file_sender, peer_id) as sender:
            yield file_sender

            async for _ in sender:
                if yield_decision():
                    await webpage.transfer_update(
                        peer_id,
                        file_sender.id,
                        file_sender.current_file
                    )

    finally:
        await _send_finalize(file_sender, peer_id)
        status_updater.close()


async def _send_setup(peer_id, selected_files):
    status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
    file_sender = files.Sender(
        Dock.peer_list.get_peer(peer_id),
        transfers_book.get_new_id(),
        selected_files,
        status_updater,
    )
    transfers_book.add_to_current(peer_id=peer_id, transfer_handle=file_sender)
    return file_sender, status_updater


@asynccontextmanager
async def _sender_helper(file_sender, peer_id):
    async with AsyncExitStack() as stack:
        try:
            may_be_confirmed = True
            connection = await stack.enter_async_context(prepare_connection(file_sender))
            file_sender.connection_made(connection)
            accepted = await asyncio.wait_for(connection.recv(1), const.DEFAULT_TRANSFER_TIMEOUT)
            print(f"{accepted=}")
            if accepted == b'\x00':
                may_be_confirmed = False
        except OSError as oe:  # unable to connect
            if const.debug:
                traceback.print_exc()
            await webpage.transfer_confirmation(peer_id, file_sender.id, False)
            raise TransferIncomplete from oe

        await webpage.transfer_confirmation(peer_id, file_sender.id, may_be_confirmed)

        if may_be_confirmed is False:
            raise TransferRejected

        yield await stack.enter_async_context(aclosing(file_sender.send_files()))


@asynccontextmanager
async def prepare_connection(sender_handle):
    _logger.debug(f"changing state to connection")  # debug
    sender_handle.state = TransferState.CONNECTING

    connector = Connector()
    async with connector.connect(sender_handle.peer_obj) as connection:
        connection.socket.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 1)
        handshake = WireData(
            header=HEADERS.CMD_FILE_CONN,
            version=sender_handle.version,
            file_id=sender_handle.id,
            peer_id=get_this_remote_peer().peer_id,
        )
        _logger.debug(f"authorization header sent for file connection {sender_handle.id}")
        await Wire.send_msg(connection, handshake)
        _logger.info(f"connection established")
        try:
            yield connection
        except OSError as oops:
            if not sender_handle.state == TransferState.PAUSED:
                _logger.warning(f"reverting state to PREPARING, failed to connect to peer",
                                exc_info=oops)
                sender_handle.state = TransferState.PREPARING
            raise


async def _send_finalize(file_sender, peer_id):
    if file_sender.state in (TransferState.COMPLETED, TransferState.ABORTING):
        transfers_book.add_to_completed(peer_id, file_sender)
    elif file_sender.state in (TransferState.PAUSED, TransferState.CONNECTING):
        transfers_book.add_to_continued(peer_id, file_sender)


@asynccontextmanager
async def file_receiver(file_req: WireData, connection: connect.Connection, status_updater):
    """
    Just a wrapper which does bookkeeping for FileReceiver object
    """

    peer_id = file_req.peer_id
    version = file_req.version
    peer_obj = await peers.get_remote_peer_at_every_cost(peer_id)
    file_handle = files.Receiver(
        peer_obj,
        file_req['file_id'],
        const.PATH_DOWNLOAD,
        status_updater
    )

    file_handle.connection_made(connection)

    transfers_book.add_to_current(file_req.id, file_handle)
    try:
        yield file_handle
    finally:
        if file_handle.state == TransferState.COMPLETED:
            transfers_book.add_to_completed(file_req.id, file_handle)
        if file_handle.state == TransferState.PAUSED:
            transfers_book.add_to_continued(file_req.id, file_handle)


def start_new_otm_file_transfer(files_list: list[Path], peers: list[RemotePeer]):
    file_sender = otm.FilesSender(
        file_list=files_list,
        peers=peers,
        timeout=3,
    )
    transfers_book.add_to_scheduled(file_sender.id, file_sender)
    return file_sender


def new_otm_request_arrived(req_data: WireData, addr):
    session = OTMSession(
        originate_id=req_data.id,
        session_id=req_data['session_id'],
        key=req_data['key'],
        fanout=req_data['fanout'],
        link_wait_timeout=req_data['link_wait_timeout'],
        adjacent_peers=req_data['adjacent_peers'],
        file_count=req_data['file_count'],
        chunk_size=req_data['chunk_size'],
    )
    this_peer = get_this_remote_peer()
    passive_endpoint_address = (this_peer.ip, connect.get_free_port())
    receiver = otm.FilesReceiver(
        session,
        passive_endpoint_address,
        this_peer.uri
    )
    transfers_book.add_to_scheduled(receiver.id, receiver)
    _logger.info(f"adding otm session to registry id={session.session_id}")
    reply = OTMInformResponse(
        peer_id=this_peer.peer_id,
        passive_addr=passive_endpoint_address,
        active_addr=this_peer.uri,
        session_key=session.key,
    )
    _logger.info(f"replying otm req with passive={reply.passive_addr} active={reply.active_addr}")
    return bytes(reply)


def FileConnectionHandler():
    async def handler(event: ConnectionEvent):
        file_req = event.handshake
        _logger.info(f"new file connection arrived transfer_id={file_req['file_id']}")
        if transfer_handle := transfers_book.check_running(file_req['file_id']):
            # if we have a transfer running with same id, just send that connection into running handle
            transfer_handle.connection_made(event.connection)
            return

            # if not await webpage.get_transfer_ok(event.handshake.peer_id):  # TODO: ask webpage
        #     await event.transport.send(b'\x00')
        #     return

        await event.connection.send(b'\x01')

        _logger.debug(f"scheduling file transfer request {file_req!r}")

        try:
            async with AsyncExitStack() as exit_stack:
                status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
                receiver_handle = await exit_stack.enter_async_context(file_receiver(
                    file_req,
                    event.connection,
                    status_updater,
                ))
                receiver = await exit_stack.enter_async_context(aclosing(receiver_handle.recv_files()))

                yield_decision = status_updater.should_yield
                async for _ in receiver:
                    if yield_decision():
                        await webpage.transfer_update(
                            file_req.peer_id,
                            receiver_handle.id,
                            receiver_handle.current_file
                        )

            status_updater.close()
        except TransferIncomplete as e:
            await webpage.transfer_incomplete(
                file_req.peer_id,
                receiver_handle.id,
                receiver_handle.current_file,
                detail=e
            )

    return handler


def OTMConnectionHandler():
    async def handler(event: ConnectionEvent):
        """
        This is the final function call related to an otm session, all other rpc' s from now are made
        internally from/to otm session relay
        """
        link_data = event.handshake
        _logger.info(f"updating otm connection from{event.connection.socket.getpeername()}")
        session_id = link_data['session_id']
        otm_relay = transfers_book.get_scheduled(session_id)
        if otm_relay:
            await otm_relay.otm_add_stream_link(event.connection, link_data)
        else:
            _logger.error(f"otm session not found with id={session_id}")
            _logger.error(f"ignoring request from {event.connection.socket.getpeername()}")

    return handler


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_dialog_handler().open_file_dialog_window)  # noqa
    if any(result) and result[0] == '.':
        return []
    return result
