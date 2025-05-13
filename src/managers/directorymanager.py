import asyncio
import logging
from contextlib import aclosing
from pathlib import Path

from src.avails import TransfersBookKeeper, WireData, const, get_dialog_handler, use
from src.avails.exceptions import TransferRejected
from src.conduit import webpage
from src.core import peers
from src.core.app import ReadOnlyAppType, provide_app_ctx
from src.core.events import ConnectionEvent
from src.net import Connector, WireIO
from src.transfers import HEADERS, TRANSFER_NOT_OK, TRANSFER_OK, TransferState, make_transfer_id
from src.transfers.files import DirReceiver, DirSender, rename_directory_with_increment
from src.transfers.status import StatusMixIn

transfers_book = TransfersBookKeeper()
_logger = logging.getLogger(__name__)


async def open_dir_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, get_dialog_handler().open_directory_dialog_window)  # noqa
    return await result


@provide_app_ctx
async def send_directory(remote_peer, dir_path, *, app_ctx=None):
    dir_path = Path(dir_path)
    transfer_id = transfers_book.get_new_id()
    dir_recv_signal_packet = WireData(
        header=HEADERS.CMD_RECV_DIR,
        peer_id=app_ctx.this_peer_id,
        transfer_id=transfer_id,
        dir_name=dir_path.name,
    )
    connector = Connector()

    async with connector.connect(remote_peer) as connection:
        await WireIO.send_msg(connection, dir_recv_signal_packet)
        await _get_confirmation(connection)

        status_mixin = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
        sender = DirSender(
            remote_peer,
            transfer_id,
            dir_path,
            status_mixin,
        )
        sender.connection_made(connection)
        _logger.info(f"sending directory: {dir_path} to {remote_peer}")
        yield_decision = status_mixin.should_yield
        async with aclosing(sender.start_transfer()) as s:
            async for _ in s:
                if yield_decision():
                    await webpage.transfer_update(sender)
        status_mixin.close()
        _logger.info(f"completed sending directory {dir_path} to {remote_peer}")


async def _get_confirmation(connection):
    try:
        confirmation = await asyncio.wait_for(connection.recv(1), const.DEFAULT_TRANSFER_TIMEOUT)
        if confirmation == TRANSFER_NOT_OK:
            _logger.info("not sending directory, other end rejected")
            raise TransferRejected()
        assert confirmation == TRANSFER_OK, "expected b'\x01' as confirmation response"

    except asyncio.TimeoutError:
        _logger.info(f"not sending directory, did not receive confirmation within {const.DEFAULT_TRANSFER_TIMEOUT}s")
        raise
    except ConnectionResetError:
        _logger.debug("not sending directory", exc_info=True)
        raise


def pause_transfer(peer_id, transfer_id):
    transfer_handle = transfers_book.get_transfer(peer_id, transfer_id)
    if not transfer_handle:
        raise ValueError(f"transfer {transfer_id} not found")

    transfer_handle.pause()
    transfers_book.add_to_continued(peer_id, transfer_handle)


def DirConnectionHandler(app_ctx: ReadOnlyAppType):
    async def handler(event: ConnectionEvent):
        connection = event.connection

        peer = await peers.get_remote_peer(event.handshake.peer_id)
        transfer_id = make_transfer_id(event)

        dir_name = event.handshake.body['dir_name']
        dir_path = rename_directory_with_increment(const.PATH_DOWNLOAD, Path(dir_name))

        status_iter = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
        receiver = DirReceiver(
            peer,
            transfer_id,
            dir_path,
            status_iter,
        )
        receiver.connection_made(connection)
        try:
            async with connection:  # acquire lock
                what = await webpage.get_transfer_ok(app_ctx.current_profile, peer.peer_id)
                if not what:
                    return await connection.send(TRANSFER_NOT_OK)

                await connection.send(TRANSFER_OK)
                transfers_book.add_to_current(transfer_id, receiver)
                _logger.info(
                    f"receiving directory from {peer}, saving at {use.shorten_path(dir_path, 40)}"
                )
                async with aclosing(receiver.start_transfer()) as loop:
                    yield_decision = status_iter.should_yield
                    async for _ in loop:
                        if yield_decision():
                            await webpage.transfer_update(receiver)

                _logger.info(f"directory received from {peer}")
                transfers_book.add_to_completed(transfer_id, receiver)
        except Exception as e:
            _logger.debug("receiving directory failed with", exc_info=e)
            if receiver.state == TransferState.PAUSED:
                transfers_book.add_to_continued(transfer_id, receiver)
            if receiver.state == TransferState.ABORTING:
                transfers_book.add_to_completed(transfer_id, receiver)

    return handler
