import asyncio
import logging
import socket
from contextlib import AsyncExitStack, aclosing, asynccontextmanager
from pathlib import Path

from src import net
from src.avails import OTMInformResponse, OTMSession, RemotePeer, TransfersBookKeeper, WireData, \
    const, get_dialog_handler
from src.avails.exceptions import TransferIncomplete, TransferRejected
from src.conduit import webpage
from src.core import peers
from src.core.app import ReadOnlyAppType, provide_app_ctx
from src.core.events import ConnectionEvent
from src.transfers import HEADERS, TRANSFER_NOT_OK, TRANSFER_OK, TransferState, files, get_transfer_id, otm
from src.transfers.abc import AbstractTransferHandle
from src.transfers.otm.relay import OTMFilesRelay
from src.transfers.status import StatusIterator, StatusMixIn

transfers_book = TransfersBookKeeper()

_logger = logging.getLogger(__name__)


@provide_app_ctx
async def send_files_to_peer(peer, selected_files, *, app_ctx=None):
    """Sends provided files to peer

    Args:
        peer(RemotePeer): peer object that receives files
        selected_files(list[str | Path]): list of file paths
        app_ctx(ReadOnlyAppType): application context to get this remote peer
    Yields:
        files.Sender object
    """

    if file_sender_handle := transfers_book.check_running(peer.peer_id):
        # if any transfer is running just attach FileItems to that transfer
        file_sender_handle.attach_files(selected_files)
        return

    file_sender, status_updater = await _send_files_setup(peer, selected_files)

    try:
        async with _sender_helper(file_sender, app_ctx.this_peer_id, HEADERS.CMD_FILE_CONN):
            await _iterate_and_update_status(status_updater, file_sender)
    finally:
        await _finalize_transfer(file_sender)
        status_updater.close()


async def _send_files_setup(peer, selected_files):
    status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
    file_sender = files.Sender(
        peer,
        transfers_book.get_new_id(),
        [files.FileItem(x, 0) for x in selected_files],
        status_updater,
    )
    transfers_book.add_to_current(peer_id=peer.peer_id, transfer_handle=file_sender)
    return file_sender, status_updater


@asynccontextmanager
async def _sender_helper(file_sender, this_peer_id, handshake_header):
    peer_id = file_sender.peer.peer_id
    async with AsyncExitStack() as stack:
        try:
            may_be_confirmed = True
            connection = await stack.enter_async_context(
                _prepare_connection(file_sender, this_peer_id, handshake_header))
            file_sender.connection_made(connection)
            accepted = await asyncio.wait_for(connection.recv(1), const.DEFAULT_TRANSFER_TIMEOUT)
            print(f"{accepted=}")  # debug
            if accepted == TRANSFER_NOT_OK:
                may_be_confirmed = False
        except OSError as oe:  # unable to connect
            await webpage.transfer_confirmation(peer_id, file_sender.id, False)
            raise TransferIncomplete from oe

        await webpage.transfer_confirmation(peer_id, file_sender.id, may_be_confirmed)

        if may_be_confirmed is False:
            raise TransferRejected

        yield connection


@asynccontextmanager
async def _prepare_connection(transfer_handle, this_peer_id, header):
    _logger.debug(f"changing state to connection")  # debug

    connector = net.Connector()
    async with connector.connect(transfer_handle.peer) as connection:
        connection.socket.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 1)
        handshake = WireData(
            header=header,
            version=transfer_handle.version,
            file_id=transfer_handle.id,
            peer_id=this_peer_id,
        )
        _logger.debug(f"authorization header sent for file connection {transfer_handle.id}")
        await net.WireIO.send_msg(connection, handshake)

        _logger.info(f"connection established")
        yield connection


async def _iterate_and_update_status(status_iter, transfer_handle: AbstractTransferHandle):
    yield_decision = status_iter.should_yield

    async with transfer_handle, aclosing(transfer_handle.start_transfer()) as loop:
        async for _ in loop:
            if yield_decision():
                await webpage.transfer_update(transfer_handle)


async def _finalize_transfer(transfer_handle):
    if transfer_handle.state in (TransferState.COMPLETED, TransferState.ABORTING):
        transfers_book.add_to_completed(transfer_handle.peer.peer_id, transfer_handle)
    elif transfer_handle.state in (TransferState.PAUSED, TransferState.CONNECTING):
        transfers_book.add_to_continued(transfer_handle.peer.peer_id, transfer_handle)


@provide_app_ctx
async def send_big_file(peer, file_list, app_ctx=None):
    file_items = [files.FileItem(x, 0) for x in file_list]
    transfer_id = transfers_book.get_new_id()
    status_iterator = StatusIterator(const.TRANSFER_STATUS_UPDATE_FREQ)
    for file_item in file_items:
        big_file_sender = files.BigFileSender(
            file_item,
            peer,
            transfer_id,
            status_iterator,
        )
        async with _sender_helper(big_file_sender, app_ctx.this_peer_id, HEADERS.CMD_BIG_FILE_CONN):
            # TODO: make a request for more connections
            await _iterate_and_update_status(
                status_iterator,
                big_file_sender
            )


def FileConnectionHandler(app_ctx):
    async def handler(event: ConnectionEvent):
        transfer_id = get_transfer_id(event)

        should_return = await _common_operations(transfer_id, event, app_ctx)
        if should_return is True:
            return

        _logger.debug(f"scheduling file transfer request {event.handshake!r}")

        await _run_file_receiver(event, transfer_id, files.Receiver)

    return handler


async def _common_operations(transfer_id, event, app_ctx):
    _logger.info(f"new file connection arrived transfer_id={transfer_id}")

    if transfer_handle := transfers_book.check_running(transfer_id):
        transfer_handle.connection_made(event.connection)
        # if we have a transfer running with same id, just send that connection into running handle
        return True

    if await webpage.get_transfer_ok(
          app_ctx.current_profile,
          event.handshake.peer_id
    ) is False:
        await event.connection.send(TRANSFER_NOT_OK)
        return True

    await event.connection.send(TRANSFER_OK)  # accepted receiving
    return False


async def _run_file_receiver(event: ConnectionEvent, transfer_id: str, transfer_handle_class):
    try:
        async with AsyncExitStack() as exit_stack:
            transfer_handle = await _recv_and_update(
                event,
                transfer_id,
                exit_stack,
                transfer_handle_class,
            )
    except TransferIncomplete as e:
        await webpage.transfer_incomplete(transfer_handle, detail=e)  # transfer_handle isn't available here yet


async def _recv_and_update(event, transfer_id, exit_stack, transfer_handle_class):
    status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
    receiver_handle = await exit_stack.enter_async_context(
        _file_receiver(event, transfer_id, status_updater, transfer_handle_class)
    )

    await _iterate_and_update_status(status_updater, receiver_handle)

    status_updater.close()
    return receiver_handle


@asynccontextmanager
async def _file_receiver(event, transfer_id, status_updater, receiver_class):
    """
    Just a wrapper which does bookkeeping for FileReceiver object
    """
    peer_id, connection = event.handshake.peer_id, event.connection

    peer_obj = await peers.get_remote_peer(peer_id)

    file_handle = receiver_class(
        peer_obj,
        transfer_id,
        const.PATH_DOWNLOAD,
        status_updater
    )

    file_handle.connection_made(connection)

    transfers_book.add_to_current(file_handle.id, file_handle)
    try:
        yield file_handle
    finally:
        await _finalize_transfer(file_handle)


@provide_app_ctx
def BigFileConnectionHandler(app_ctx):
    async def handler(event: ConnectionEvent):
        transfer_id = get_transfer_id(event)

        should_return = await _common_operations(transfer_id, event, app_ctx)
        if should_return is True:
            return

        _logger.debug(f"scheduling big file transfer request {event.handshake!r}")

        await _run_file_receiver(event, transfer_id, files.BigFileReceiver)

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
        assert isinstance(otm_relay, OTMFilesRelay), "expected otm_relay object"

        if otm_relay:
            await otm_relay.otm_add_stream_link(event.connection, link_data)
        else:
            _logger.error(f"otm session not found with id={session_id}")

    return handler


@provide_app_ctx
def start_new_otm_file_transfer(files_list: list[Path], peers: list[RemotePeer], *, app_ctx=None):
    file_sender = otm.FilesSender(
        file_list=files_list,
        this_peer=app_ctx.this_remote_peer,
        peers=peers,
        timeout=3,
    )
    transfers_book.add_to_scheduled(file_sender.id, file_sender)
    return file_sender


@provide_app_ctx
def new_otm_request_arrived(req_data: WireData, _, *, app_ctx):
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
    this_peer = app_ctx.this_remote_peer
    passive_endpoint_address = (this_peer.ip, net.get_free_port())
    receiver = otm.FilesReceiver(
        session,
        app_ctx.this_remote_peer,
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


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_dialog_handler().open_file_dialog_window)  # noqa
    if any(result) and result[0] == '.':
        return []
    return result
