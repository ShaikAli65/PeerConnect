import asyncio
import logging
from contextlib import AsyncExitStack, aclosing, asynccontextmanager
from pathlib import Path

from src.avails import DataWeaver, OTMInformResponse, OTMSession, RemotePeer, TransfersBookKeeper, WireData, connect, \
    const, get_dialog_handler
from src.avails.events import ConnectionEvent
from src.avails.exceptions import TransferIncomplete
from src.core import Dock, get_this_remote_peer
from src.transfers import TransferState, files, otm
from src.webpage_handlers import pagehandle
from src.webpage_handlers.headers import HANDLE

transfers_book = TransfersBookKeeper()

_logger = logging.getLogger(__name__)


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_dialog_handler().open_file_dialog_window)  # noqa
    if any(result) and result[0] == '.':
        return []
    return result


@asynccontextmanager
async def send_files_to_peer(peer_id, selected_files):
    """Sends provided files to peer with ``peer_id``
    Gets peer information from peers module

    Args:
        peer_id(str): id of peer to send file to
        selected_files(list[str | Path]): list of file paths

    Yields:
        An async generator that yields ``(FileItem, int)`` tuple, second element contains number saying how much file was transferred
    """

    if file_sender_handle := transfers_book.check_running(peer_id):
        # if any transfer is running just attach FileItems to that transfer
        file_sender_handle.attach_files(selected_files)
        return

    # create a new file sender
    file_sender = files.Sender(
        selected_files,
        Dock.peer_list.get_peer(peer_id),
        transfers_book.get_new_id() + str(peer_id),
        status_yield_frequency=const.TRANSFER_STATUS_FREQ
    )

    transfers_book.add_to_current(peer_id=peer_id, transfer_handle=file_sender)
    try:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(file_sender.prepare_connection())
            sender = await stack.enter_async_context(aclosing(file_sender.send_files()))
            yield sender
            # async for status in sender:
            #     yield status
    finally:
        if file_sender.state == TransferState.PAUSED:
            transfers_book.add_to_continued(peer_id, file_sender)

        if file_sender.state in (TransferState.COMPLETED, TransferState.ABORTING):
            transfers_book.add_to_completed(peer_id, file_sender)


@asynccontextmanager
async def file_receiver(file_req: WireData, connection):
    """
    Just a wrapper function which does bookkeeping for FileReceiver object
    """
    peer_id = file_req.id
    version = file_req.version
    file_transfer_id = file_req['file_id']

    file_handle = files.Receiver(
        peer_id,
        file_transfer_id,
        const.PATH_DOWNLOAD,
        yield_freq=const.TRANSFER_STATUS_FREQ
    )
    file_handle.connection_arrived(connection)
    transfers_book.add_to_current(file_req.id, file_handle)

    yield file_handle

    if file_handle.state == TransferState.COMPLETED:
        transfers_book.add_to_completed(file_req.id, file_handle)
    if file_handle.state == TransferState.PAUSED:
        transfers_book.add_to_continued(file_req.id, file_handle)


def start_new_otm_file_transfer(files_list: list[Path], peers: list[RemotePeer]):
    file_sender = otm.FilesSender(file_list=files_list, peers=peers, timeout=3)  # check regarding timeouts
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
        with event.transport.socket:
            file_req = event.handshake
            _logger.info("new file connection arrived", extra={'id': file_req['file_id']})
            _logger.debug(f"scheduling file transfer request {file_req!r}")

            try:
                async with AsyncExitStack() as exit_stack:
                    receiver_handle = await exit_stack.enter_async_context(
                        file_receiver(file_req, event.transport.socket)
                    )
                    receiver = await exit_stack.enter_async_context(
                        aclosing(receiver_handle.recv_files())
                    )

                    async for file_item, received in receiver:
                        status_update = DataWeaver(
                            header=HANDLE.TRANSFER_UPDATE,
                            content={
                                'item_path': str(file_item.path),
                                'received': received,
                                'transfer_id': receiver_handle.id,
                            },
                            peer_id=file_req.peer_id,
                        )
                        pagehandle.dispatch_data(status_update)

            except TransferIncomplete as e:
                status_update = DataWeaver(
                    header=HANDLE.TRANSFER_UPDATE,
                    content={
                        'item_path': str(file_item.path),
                        'received': received,
                        'transfer_id': receiver_handle.id,
                        'cancelled': True,
                        'error': str(e),
                    },
                    peer_id=file_req.peer_id,
                )
                pagehandle.dispatch_data(status_update)

    return handler


def OTMConnectionHandler():
    async def handler(event: ConnectionEvent):
        """
        This is the final function call related to an otm session, all other rpc' s from now are made
        internally from/to otm session relay
        """
        connection = event.transport.socket
        link_data = event.handshake
        _logger.info("updating otm connection", extra={'addr': connection.getpeername()})
        session_id = link_data['session_id']
        otm_relay = transfers_book.get_scheduled(session_id)
        if otm_relay:
            await otm_relay.otm_add_stream_link(connection, link_data)
        else:
            _logger.error(f"otm session not found with id={session_id}")
            _logger.error(f"ignoring request from {connection.getpeername()}")

    return handler
