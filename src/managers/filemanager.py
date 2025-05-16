import asyncio
import logging
import socket
import struct
from contextlib import AsyncExitStack, aclosing, asynccontextmanager
from pathlib import Path
from typing import Awaitable, Callable

from src import net
from src.avails import (
    OTMInformResponse,
    OTMSession,
    RemotePeer,
    TransfersBookKeeper,
    WireData,
    const,
    get_dialog_handler,
)
from src.avails.exceptions import TransferIncomplete, TransferRejected
from src.conduit import webpage
from src.core import peers
from src.core.app import ReadOnlyAppType, provide_app_ctx
from src.net.events import ConnectionEvent
from src.transfers import (
    HEADERS,
    TRANSFER_NOT_OK,
    TRANSFER_OK,
    TransferState,
    files,
    make_transfer_id,
    otm,
)
from src.transfers.abc import AbstractTransferHandle
from src.transfers.files import FileItem, add_error_ext, validatename
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

    if file_sender_handle := transfers_book.get_running_transfer(peer.peer_id):
        # if any transfer is running just attach FileItems to that transfer
        file_sender_handle.attach_files(selected_files)
        return

    status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
    file_sender = files.Sender(
        peer,
        transfers_book.get_new_id(),
        [files.FileItem(x, 0) for x in selected_files],
        status_updater,
    )
    transfers_book.add_to_current(peer_id=peer.peer_id, transfer_handle=file_sender)

    try:
        async with sender_helper(
              file_sender, app_ctx.this_peer_id, HEADERS.CMD_FILE_CONN
        ) as connection:
            await iterate_and_update_status(status_updater, file_sender, connection)
    except TransferRejected as tr:
        _logger.debug("Transfer rejected:", exc_info=tr)
    finally:
        await finalize_transfer(file_sender)
        await status_updater.close()


@asynccontextmanager
async def sender_helper(sender, this_peer_id, handshake_header, **extras):
    try:
        async with _prepare_connection(
              sender,
              this_peer_id,
              handshake_header,
              **extras
        ) as connection:
            await get_confirmation(sender, connection)
            yield connection
    except OSError as oe:  # unable to connect
        await webpage.transfer_confirmation(sender, False)
        raise TransferIncomplete from oe


@asynccontextmanager
async def _prepare_connection(transfer_handle, this_peer_id, header, **extras):
    connector = net.Connector()
    async with connector.connect(transfer_handle.peer) as connection:
        handshake = WireData(
            header=header,
            version=extras.pop("version", transfer_handle.version),
            transfer_id=extras.pop("transfer_id", transfer_handle.id),
            peer_id=extras.pop("peer_id", this_peer_id),
            **extras,
        )
        _logger.debug(
            f"authorization header sent for transfer {header=}, {transfer_handle.id=}"
        )
        await net.WireIO.send_msg(connection, handshake)
        _logger.info(f"connection established")

        # enable NAGLE algorithm, as we are dealing with file transfers (which are usually big)
        connection.socket.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 0)
        yield connection


async def get_confirmation(transfer_handle, connection):
    try:
        confirmation = await asyncio.wait_for(
            connection.recv(1), const.DEFAULT_TRANSFER_TIMEOUT
        )
        if confirmation == TRANSFER_NOT_OK:
            _logger.info(f"not sending: {transfer_handle} :, other end rejected")
            raise TransferRejected(f"{confirmation=}")
        assert (
              confirmation == TRANSFER_OK
        ), f"expected {TRANSFER_OK=} as confirmation response"
        await webpage.transfer_confirmation(transfer_handle, bool(confirmation))
        return True
    except asyncio.TimeoutError as te:
        _logger.info(
            f"not sending: {transfer_handle} :, did not receive confirmation within {const.DEFAULT_TRANSFER_TIMEOUT}s"
        )
        await webpage.transfer_confirmation(transfer_handle, False)
        raise TransferRejected from te
    except ConnectionError as ce:
        _logger.debug(f"not sending {transfer_handle}", exc_info=True)
        await webpage.transfer_confirmation(transfer_handle, False)
        raise TransferRejected from ce


async def iterate_and_update_status(
      status_iter, transfer_handle: AbstractTransferHandle, *connections
):
    yield_decision = status_iter.should_yield

    async with transfer_handle, aclosing(transfer_handle.start_transfer()) as loop:
        for con in connections:
            transfer_handle.connection_made(con)
        async for _ in loop:
            if yield_decision():
                await webpage.transfer_update(transfer_handle)


async def finalize_transfer(transfer_handle, transfers_book=transfers_book):
    _logger.debug(f"finalizing transfer= {transfer_handle=}")
    if transfer_handle.state in (TransferState.COMPLETED, TransferState.ABORTING):
        transfers_book.add_to_completed(transfer_handle.peer.peer_id, transfer_handle)
    elif transfer_handle.state in (TransferState.PAUSED, TransferState.CONNECTING):
        transfers_book.add_to_continued(transfer_handle.peer.peer_id, transfer_handle)


@provide_app_ctx
async def send_big_file(peer, file_list, app_ctx=None):
    file_item = files.FileItem(file_list[0], 0)
    transfer_id = transfers_book.get_new_id()
    status_iterator = StatusIterator(const.TRANSFER_STATUS_UPDATE_FREQ)
    big_file_sender = files.BigFileSender(
        file_item,
        peer,
        transfer_id,
        status_iterator,
    )
    async with AsyncExitStack() as exit_stack:
        connection1 = await exit_stack.enter_async_context(
            sender_helper(
                big_file_sender,
                app_ctx.this_peer_id,
                HEADERS.CMD_BIG_FILE_CONN,
            )
        )
        await connection1.send(
            struct.pack("!I", len(file_item_bytes := bytes(file_item)))
            + file_item_bytes
        )

        async def f():
            await asyncio.sleep(1.3)
            connection2 = await exit_stack.enter_async_context(
                _prepare_connection(
                    big_file_sender, app_ctx.this_peer_id, HEADERS.CMD_BIG_FILE_CONN
                )
            )
            _logger.debug("ADDING CONNECTION, 🔥🔥")
            big_file_sender.connection_made(connection2)
            return connection2

        asyncio.create_task(f())

        await iterate_and_update_status(
            status_iterator,
            big_file_sender,
            # c,
            connection1,
            # connection1, connection2,
        )


# RECEIVERS


def FileConnectionHandler(app_ctx):
    async def handler(event: ConnectionEvent):
        transfer_id = make_transfer_id(event)

        transfer_handle, should_return = await basic_recv(transfer_id, event, app_ctx)
        if should_return is True:
            await transfer_handle.done.wait()
            return

        _logger.debug(f"scheduling transfer request {event.handshake!r}")

        await run_receiver(event, transfer_id, make_receiver)

    async def make_receiver(transfer_id, peer_obj):
        status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
        return files.Receiver(
            transfer_id, peer_obj, const.PATH_DOWNLOAD, status_updater
        )

    return handler


async def basic_recv(
      transfer_id, event, app_ctx, transfers_book=transfers_book  # noqa
) -> tuple[AbstractTransferHandle | None, bool]:
    """
    Performs a basic check of existing transfer handle with `transfer_id`
    If found then attaches the connection found in the event to the existing handle
    returns the transfer_handle and boolean=True that confirms no need of further processing

    If a transfer handle not found then gets confirmation from webpage, sends the confirmation
    via connection inside the event, returns boolean stating whether to proceed with the transfer or not.

    """

    _logger.info(f"new file connection arrived transfer_id={transfer_id}")
    if transfer_handle := transfers_book.get_running_transfers(
          event.handshake.peer_id, transfer_id
    ):
        # if we have a transfer running with same id,
        # just send that connection into running handle
        transfer_handle.connection_made(event.connection)
        return transfer_handle, True

    if (
          await webpage.get_transfer_ok(app_ctx.current_profile, event.handshake.peer_id)
          is False
    ):
        await event.connection.send(TRANSFER_NOT_OK)
        return transfer_handle, True

    await event.connection.send(TRANSFER_OK)  # accepted receiving
    return transfer_handle, False


TransferHandleFactoryKind = Callable[
    [RemotePeer, str | int], Awaitable[AbstractTransferHandle]
]


async def run_receiver(
      event: ConnectionEvent,
      transfer_id: str,
      handle_factory: TransferHandleFactoryKind,
      transfer_book=transfers_book,
):
    transfer_handle = None
    try:
        receiver_handle = await _file_receiver(event, transfer_id, handle_factory)
        status_updater = receiver_handle.status_updater
        await iterate_and_update_status(
            status_updater, receiver_handle, event.connection
        )
        await status_updater.close()
    except TransferIncomplete as e:
        if transfer_handle:
            await webpage.transfer_incomplete(transfer_handle, detail=e)
        # transfer_handle isn't available here yet
    finally:
        if transfer_handle is not None:
            await finalize_transfer(transfer_handle, transfers_book=transfer_book)


async def _file_receiver(
      event, transfer_id, transfer_factory: TransferHandleFactoryKind
):
    """
    Just a wrapper which does bookkeeping for FileReceiver object

    """

    peer_obj = await peers.get_remote_peer(event.handshake.peer_id)
    file_handle = await transfer_factory(peer_obj, transfer_id)

    transfers_book.add_to_current(event.handshake.peer_id, file_handle)
    return file_handle


def BigFileConnectionHandler(app_ctx):
    main_file = None

    async def handler(event: ConnectionEvent):
        nonlocal main_file
        _logger.debug(f"new big file transfer request arrived, {event=}")
        transfer_id = make_transfer_id(event)

        transfer_handle, should_return = await basic_recv(transfer_id, event, app_ctx)
        if should_return is True:
            await transfer_handle.done.wait()
            return

        file_item_size = await net.recv_int(event.connection.recv)
        try:
            main_file = FileItem.load_from(
                await event.connection.recv(file_item_size),
                const.PATH_DOWNLOAD,
            )
        except TypeError:
            # ill formed file item
            _logger.error("ill formed file-item, rejecting transfer")
            watcher = net.Watcher()
            await watcher.request_closing(event.connection)
            return

        validatename(main_file, const.PATH_DOWNLOAD)
        _logger.debug(f"scheduling big file transfer request {event.handshake!r}")
        try:
            await run_receiver(event, transfer_id, make_big_receiver)
        except Exception:
            if main_file:
                add_error_ext(main_file, const.PATH_DOWNLOAD, const.FILE_ERROR_EXT)
            raise

    async def make_big_receiver(peer_obj, transfer_id):
        status_updater = StatusIterator(const.TRANSFER_STATUS_UPDATE_FREQ)
        fr = files.BigFileReceiver(
            peer_obj, transfer_id, const.PATH_DOWNLOAD, status_updater
        )
        fr.current_file = main_file
        return fr

    return handler


def OTMConnectionHandler():
    async def handler(event: ConnectionEvent):
        """
        This is the final function call related to an otm session, all other rpc' s from now are made
        internally from/to otm session relay
        """
        link_data = event.handshake
        _logger.info(
            f"updating otm connection from{event.connection.socket.getpeername()}"
        )
        session_id = link_data["session_id"]
        otm_relay = transfers_book.get_scheduled(session_id)
        assert isinstance(otm_relay, OTMFilesRelay), "expected otm_relay object"

        if otm_relay:
            await otm_relay.otm_add_stream_link(event.connection, link_data)
        else:
            _logger.error(f"otm session not found with id={session_id}")

    return handler


@provide_app_ctx
def start_new_otm_file_transfer(
      files_list: list[Path], peers: list[RemotePeer], *, app_ctx=None
):
    file_sender = otm.FilesSender(
        file_list=files_list,
        this_peer=app_ctx.this_remote_peer,
        peers=peers,
        timeout=3,
    )
    transfers_book.add_to_scheduled(file_sender)
    return file_sender


@provide_app_ctx
def new_otm_request_arrived(req_data: WireData, _, *, app_ctx):
    session = OTMSession(
        originate_id=req_data.id,
        session_id=req_data["session_id"],
        key=req_data["key"],
        fanout=req_data["fanout"],
        link_wait_timeout=req_data["link_wait_timeout"],
        adjacent_peers=req_data["adjacent_peers"],
        file_count=req_data["file_count"],
        chunk_size=req_data["chunk_size"],
    )
    this_peer = app_ctx.this_remote_peer
    passive_endpoint_address = (this_peer.ip, net.get_free_port())
    receiver = otm.FilesReceiver(
        session, app_ctx.this_remote_peer, passive_endpoint_address, this_peer.uri
    )
    transfers_book.add_to_scheduled(receiver)
    _logger.info(f"adding otm session to registry id={session.session_id}")
    reply = OTMInformResponse(
        peer_id=this_peer.peer_id,
        passive_addr=passive_endpoint_address,
        active_addr=this_peer.uri,
        session_key=session.key,
    )
    _logger.info(
        f"replying otm req with passive={reply.passive_addr} active={reply.active_addr}"
    )
    return bytes(reply)


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, get_dialog_handler().open_file_dialog_window
    )  # noqa
    if any(result) and result[0] == ".":
        return []
    return result
