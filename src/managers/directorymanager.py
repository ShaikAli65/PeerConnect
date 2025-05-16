import asyncio
import logging
from pathlib import Path

from src.avails import TransfersBookKeeper, const, get_dialog_handler
from src.core.app import ReadOnlyAppType, provide_app_ctx
from src.managers.filemanager import (
    basic_recv,
    finalize_transfer,
    iterate_and_update_status,
    run_receiver,
    sender_helper,
)
from src.net.events import ConnectionEvent
from src.transfers import HEADERS, make_transfer_id
from src.transfers.files import DirReceiver, DirSender, rename_directory_with_increment
from src.transfers.status import StatusMixIn

transfers_book = TransfersBookKeeper()
_logger = logging.getLogger(__name__)


async def open_dir_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(
        None, get_dialog_handler().open_directory_dialog_window
    )  # noqa
    return await result


@provide_app_ctx
async def send_directory(remote_peer, dir_path: Path, *, app_ctx=None):
    status_mixin = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
    sender = DirSender(
        remote_peer,
        transfers_book.get_new_id(),
        dir_path,
        status_mixin,
    )
    transfers_book.add_to_current(remote_peer.peer_id, sender)
    _logger.debug(f"initiating new directory transfer to {remote_peer}")
    try:
        async with sender_helper(
              sender,
              app_ctx.this_peer_id,
              HEADERS.CMD_DIR_CONN,
              dir_name=dir_path.name,
        ) as connection:
            _logger.info(f"sending directory: {dir_path} to {remote_peer}")
            await iterate_and_update_status(status_mixin, sender, connection)
            _logger.info(f"completed sending directory {dir_path} to {remote_peer}")
    except Exception as exp:
        _logger.debug(f"failed to send directory to {remote_peer}", exc_info=exp)
        raise
    finally:
        await finalize_transfer(sender, transfers_book)
        await status_mixin.close()


def pause_transfer(peer_id, transfer_id):
    transfer_handle = transfers_book.get_transfer(peer_id, transfer_id)
    if not transfer_handle:
        raise ValueError(f"transfer {transfer_id} not found")

    transfer_handle.pause()
    transfers_book.add_to_continued(peer_id, transfer_handle)


def DirConnectionHandler(app_ctx: ReadOnlyAppType):
    async def handler(event: ConnectionEvent):

        async def make_dir_receiver(peer, _transfer_id):
            dir_path = Path(event.handshake.body["dir_name"])
            renamed_dir_path = rename_directory_with_increment(
                const.PATH_DOWNLOAD, dir_path
            )
            status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
            return DirReceiver(
                peer,
                _transfer_id,
                renamed_dir_path,
                status_updater,
            )

        transfer_id = make_transfer_id(event)
        if t := transfers_book.get_transfer(event.handshake.peer_id, transfer_id):
            transfers_book.remove_transfer(event.handshake.peer_id, t)
            # if we get same transfer-id again, remove the existing transfer, this will make sure
            # `should_return` is False

        transfer_handle, should_return = await basic_recv(
            transfer_id, event, app_ctx, transfers_book
        )
        if should_return is True:
            await transfer_handle.done.wait()
            return

        _logger.debug(f"scheduling transfer request {event.handshake!r}")
        await run_receiver(
            event, transfer_id, make_dir_receiver, transfer_book=transfers_book
        )

    return handler
