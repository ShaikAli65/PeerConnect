from __future__ import annotations

import asyncio
import logging
import socket
import struct
from contextlib import AsyncExitStack, aclosing, asynccontextmanager, suppress
from pathlib import Path
from typing import Awaitable, Callable

from src import net
from src.avails import (
    OTMInformResponse,
    OTMSession,
    RemotePeer,
    TransferBookBucket, TransfersBook, WireData,
    const,
)
from src.avails.exceptions import (
    TransferIncomplete,
    TransferRejected,
)
from src.core import app_events
from src.core.user_prompts import UserPrompts
from src.managers import ProfileManager
from src.managers.connection import ConnectionManager
from src.net.events import ConnectionContext, ConnectionEvent
from src.transfers import (
    HEADERS,
    TRANSFER_NOT_OK,
    TRANSFER_OK,
    TransferState,
    files,
    make_transfer_id,
    otm,
)
from src.transfers.abc import AbstractTransferHandle, TransferEvents, TransferKind
from src.transfers.files import FileItem, add_error_ext, validatename
from src.transfers.otm.relay import OTMFilesRelay
from src.transfers.status import StatusIterator, StatusMixIn

_logger = logging.getLogger(__name__)


def init_transfer_manager(
      this_peer: RemotePeer,
      current_profile: ProfileManager,
      connection_manager: ConnectionManager,
      user_prompts: UserPrompts,
      app_event_bus: app_events.AppEventsBus,
) -> TransferManager:
    transfer_consent = TransferConsent(current_profile, user_prompts)
    tm = TransferManager(
        this_peer_id=this_peer.peer_id,
        connection_manager=connection_manager,
        default_download_path=const.PATH_DOWNLOAD,
        transfer_consenter=transfer_consent,
        transfer_events=AppEventTransferEvents(app_event_bus),
    )

    return tm


class TransferConsent:
    """Owns transfer consent decisions and wire-level confirmation bytes.

    Receiving side:
        * checks persisted peer preferences on ``current_profile``
        * asks the user when no preference exists
        * persists "remember my choice" responses through ``current_profile``
        * sends ``TRANSFER_OK`` / ``TRANSFER_NOT_OK`` to the requesting peer

    Sending side:
        * waits for the receiving peer's one-byte confirmation response
        * raises ``TransferRejected`` on rejection, timeout, or invalid response
    """
    def __init__(
          self,
          current_profile: ProfileManager,
          user_prompts: UserPrompts,
          *,
          timeout=const.DEFAULT_TRANSFER_TIMEOUT,
    ):
        self.current_profile = current_profile
        self.user_prompts = user_prompts
        self.timeout = timeout

    async def confirm_receiving(self, peer_id: str) -> bool:
        if (agreed := self._remembered_choice(peer_id)) is not None:
            return bool(agreed)

        confirmed, remember = await self.user_prompts.ask_transfer_consent(peer_id)

        if remember is not None:
            await self.current_profile.add_transfers_agreed(peer_id, remember)

        return confirmed

    async def respond_to_incoming_transfer(self, connection, peer_id: str) -> bool:
        accepted = await self.confirm_receiving(peer_id)
        await connection.send(TRANSFER_OK if accepted else TRANSFER_NOT_OK)
        return accepted

    async def wait_for_receiver_confirmation(self, transfer_handle, connection) -> None:
        try:
            confirmation = await asyncio.wait_for(
                connection.recv(1),
                self.timeout,
            )
        except (asyncio.TimeoutError, ConnectionError) as exp:
            raise TransferRejected from exp

        if confirmation == TRANSFER_NOT_OK:
            raise TransferRejected(f"{confirmation=}")

        if confirmation != TRANSFER_OK:
            raise TransferRejected(f"unexpected transfer confirmation {confirmation!r}")

    def _remembered_choice(self, peer_id: str):
        return getattr(self.current_profile, "transfers_agreed", {}).get(peer_id, None)


class AppEventTransferEvents(TransferEvents):
    def __init__(self, app_event_bus: app_events.AppEventsBus):
        self.app_event_bus = app_event_bus

    async def transfer_started(self, transfer: AbstractTransferHandle):
        self.app_event_bus.publish(
            app_events.TransferStarted(
                transfer_id=str(transfer.id),
                peer_id=transfer.peer.peer_id,
                kind=self._transfer_kind(transfer),
            )
        )

    async def transfer_update(self, transfer: AbstractTransferHandle):
        self.app_event_bus.publish(
            app_events.TransferProgressUpdated(
                transfer_id=str(transfer.id),
                peer_id=transfer.peer.peer_id,
                item_path=self._current_item_path(transfer),
                progress=transfer.status_updater.current_status,
            )
        )

    async def transfer_completed(self, transfer: AbstractTransferHandle):
        self.app_event_bus.publish(
            app_events.TransferCompleted(
                transfer_id=str(transfer.id),
                peer_id=transfer.peer.peer_id,
            )
        )

    async def transfer_incomplete(self, transfer: AbstractTransferHandle, error):
        self.app_event_bus.publish(
            app_events.TransferIncomplete(
                transfer_id=str(transfer.id),
                peer_id=transfer.peer.peer_id,
                item_path=self._current_item_path(transfer),
                progress=transfer.status_updater.current_status,
                error=str(error) if error else None,
            )
        )

    async def transfer_confirmation(self, transfer: AbstractTransferHandle, confirmation_details):
        self.app_event_bus.publish(
            app_events.TransferConfirmation(
                transfer_id=str(transfer.id),
                peer_id=transfer.peer.peer_id,
                confirmed=bool(confirmation_details),
            )
        )

    @staticmethod
    def _current_item_path(transfer: AbstractTransferHandle):
        current = transfer.current_transfer
        return str(current.path) if current is not None else None

    @staticmethod
    def _transfer_kind(transfer: AbstractTransferHandle):
        record = getattr(transfer, "kind", None)
        return getattr(record, "value", record)


class TransferManager:
    PeerResolver = Callable[[str], Awaitable[RemotePeer | None]]

    def __init__(
          self,
          *,
          this_peer_id: str,
          connection_manager: ConnectionManager,
          default_download_path: Path,
          transfer_consenter: TransferConsent,
          transfer_events: TransferEvents,
    ):
        self.this_peer_id = this_peer_id
        self.default_download_path = default_download_path
        self.transfer_consenter = transfer_consenter
        self.transfer_events = transfer_events
        self.connection_manager = connection_manager
        self.transfers_book = TransfersBook()
        self.register_connection_handlers(connection_manager.connection_router)

    def connection_handlers(self):
        return {
            HEADERS.CMD_FILE_CONN: self.file_connection_handler,
            HEADERS.CMD_BIG_FILE_CONN: self.big_file_connection_handler,
            HEADERS.CMD_DIR_CONN: self.directory_connection_handler,
            HEADERS.OTM_UPDATE_STREAM_LINK: self.otm_connection_handler,
        }

    def register_connection_handlers(self, router):
        for header, handler in self.connection_handlers().items():
            router.register_handler(header, handler)
        return router

    async def send_files(
          self,
          peer: RemotePeer,
          selected_files: list[Path],
    ) -> AbstractTransferHandle:
        file_items = [files.FileItem(path, 0) for path in selected_files]

        status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
        sender = files.Sender(
            peer,
            self.transfers_book.get_new_id(),
            file_items,
            status_updater,
        )
        self._add_current(sender, TransferKind.FILES)

        try:
            async with self._sender_connection(sender, HEADERS.CMD_FILE_CONN) as connection:
                await self._run_transfer(status_updater, sender, connection)
        except TransferRejected as exp:
            await self.transfer_events.transfer_confirmation(sender, False)
            await self.transfer_events.transfer_incomplete(sender, exp)
            raise
        finally:
            await self._finalize(sender)
            await status_updater.close()

        return sender

    async def send_directory(
          self,
          peer: RemotePeer,
          dir_path: Path,
    ) -> AbstractTransferHandle:
        status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
        sender = files.DirSender(
            peer,
            self.transfers_book.get_new_id(),
            dir_path,
            status_updater,
        )
        self._add_current(sender, TransferKind.DIRECTORY)

        try:
            async with self._sender_connection(
                  sender,
                  HEADERS.CMD_DIR_CONN,
                  dir_name=dir_path.name,
            ) as connection:
                await self._run_transfer(status_updater, sender, connection)
        except TransferRejected as exp:
            await self.transfer_events.transfer_confirmation(sender, False)
            await self.transfer_events.transfer_incomplete(sender, exp)
            raise
        finally:
            await self._finalize(sender)
            await status_updater.close()

        return sender

    async def send_big_file(
          self,
          peer: RemotePeer,
          file_path: Path,
    ) -> AbstractTransferHandle:
        file_item = files.FileItem(file_path, 0)
        status_iterator = StatusIterator(const.TRANSFER_STATUS_UPDATE_FREQ)
        sender = files.BigFileSender(
            file_item,
            peer,
            self.transfers_book.get_new_id(),
            status_iterator,
        )
        self._add_current(sender, TransferKind.BIG_FILE)

        try:
            async with AsyncExitStack() as exit_stack:
                connection1 = await exit_stack.enter_async_context(
                    self._sender_connection(sender, HEADERS.CMD_BIG_FILE_CONN)
                )
                await connection1.send(
                    struct.pack("!I", len(file_item_bytes := bytes(file_item)))
                    + file_item_bytes
                )
                # TODO: how to add more connections?
                await self._run_transfer(status_iterator, sender, connection1)

        except TransferRejected as exp:
            await self.transfer_events.transfer_confirmation(sender, False)
            await self.transfer_events.transfer_incomplete(sender, exp)
            raise
        finally:
            await self._finalize(sender)
            await status_iterator.close()

        return sender

    def pause(self, transfer_id):
        transfer_handle = self.transfers_book.get_running(transfer_id)
        if not transfer_handle:
            raise ValueError(f"transfer {transfer_id} not found")

        transfer_handle.pause()
        self.transfers_book.move(transfer_handle.id, TransferBookBucket.SCHEDULED)
        return transfer_handle

    def get_transfer(self, transfer_id):
        return self.transfers_book.get(transfer_id)

    async def cancel(self, transfer_id):
        transfer_handle = self.get_transfer(transfer_id)
        if not transfer_handle:
            raise ValueError(f"transfer {transfer_id} not found")

        await transfer_handle.cancel()
        await self._finalize(transfer_handle)
        return transfer_handle

    async def file_connection_handler(self, event_ctx: ConnectionContext):
        async with event_ctx as event:
            transfer_id = make_transfer_id(event)
            transfer_handle, should_return = await self._accept_or_attach(event, transfer_id)
            if should_return:
                if transfer_handle:
                    await transfer_handle.done.wait()
                return

            await self._run_receiver(
                event,
                transfer_id,
                self._make_file_receiver,
                TransferKind.FILES,
            )

    async def directory_connection_handler(self, event_ctx: ConnectionContext):
        async with event_ctx as event:
            transfer_id = make_transfer_id(event)

            transfer_handle, should_return = await self._accept_or_attach(event, transfer_id)
            if should_return:
                if transfer_handle:
                    await transfer_handle.done.wait()
                return

            await self._run_receiver(
                event,
                transfer_id,
                lambda peer, _transfer_id: self._make_directory_receiver(
                    peer,
                    _transfer_id,
                    Path(event.handshake.body["dir_name"]),
                ),
                TransferKind.DIRECTORY,
            )

    async def big_file_connection_handler(self, event_ctx: ConnectionContext):
        async with event_ctx as event:
            transfer_id = make_transfer_id(event)
            transfer_handle, should_return = await self._accept_or_attach(event, transfer_id)
            if should_return:
                if transfer_handle:
                    await transfer_handle.done.wait()
                return

            file_item_size = await net.recv_int(event.connection.recv)
            try:
                main_file = FileItem.load_from(
                    await event.connection.recv(file_item_size),
                    self.default_download_path,
                )
            except TypeError:
                _logger.error("ill formed file item, rejecting big-file transfer")
                watcher = net.Watcher()
                await watcher.request_closing(event.connection)
                return

            validatename(main_file, self.default_download_path)
            try:
                await self._run_receiver(
                    event,
                    transfer_id,
                    lambda peer, _transfer_id: self._make_big_file_receiver(
                        peer,
                        _transfer_id,
                        main_file,
                    ),
                    TransferKind.BIG_FILE,
                )
            except Exception:
                add_error_ext(main_file, self.default_download_path, const.FILE_ERROR_EXT)
                raise

    async def otm_connection_handler(self, event_ctx: ConnectionContext):
        async with event_ctx as event:
            link_data = event.handshake
            session_id = link_data["session_id"]
            otm_relay = self.transfers_book.get_scheduled(session_id)

            if not isinstance(otm_relay, OTMFilesRelay):
                _logger.error(f"otm session not found with id={session_id}")
                return

            await otm_relay.otm_add_stream_link(event.connection, link_data)

    def start_new_otm_file_transfer(
          self,
          files_list: list[Path],
          peers_to_send: list[RemotePeer],
          this_remote_peer: RemotePeer,
    ):
        sender = otm.FilesSender(
            file_list=files_list,
            this_peer=this_remote_peer,
            peers=peers_to_send,
            timeout=3,
        )
        self.transfers_book.move(sender.id, TransferBookBucket.SCHEDULED)
        return sender

    def new_otm_request_arrived(self, req_data: WireData, this_peer: RemotePeer):
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
        passive_endpoint_address = (this_peer.ip, net.get_free_port())
        receiver = otm.FilesReceiver(
            session,
            this_peer,
            passive_endpoint_address,
            this_peer.uri,
        )
        self.transfers_book.move(receiver.id, TransferBookBucket.SCHEDULED)
        return bytes(
            OTMInformResponse(
                peer_id=this_peer.peer_id,
                passive_addr=passive_endpoint_address,
                active_addr=this_peer.uri,
                session_key=session.key,
            )
        )

    async def retry(self, transfer_id):
        transfer_handle = self.transfers_book.get_scheduled(transfer_id)
        assert transfer_handle is not None, f"{transfer_id=} handle not found to retry"

    async def _add_connection(
          self,
          exit_stack: AsyncExitStack,
          transfer_handle: AbstractTransferHandle,
    ):
        connection = await exit_stack.enter_async_context(
            self._prepare_connection(transfer_handle, HEADERS.CMD_BIG_FILE_CONN)
        )
        assert transfer_handle.state == TransferState.RECEIVING, \
            "transfer handle is not in receiving state to add connection"
        transfer_handle.connection_made(connection)
        return connection

    @asynccontextmanager
    async def _sender_connection(
          self,
          transfer_handle: AbstractTransferHandle,
          handshake_header,
          **extras,
    ):
        async with self._prepare_connection(
              transfer_handle,
              handshake_header,
              **extras,
        ) as connection:
            await self.transfer_consenter.wait_for_receiver_confirmation(transfer_handle, connection)
            yield connection

    @asynccontextmanager
    async def _prepare_connection(
          self,
          transfer_handle: AbstractTransferHandle,
          header,
          **extras,
    ):
        async with self.connection_manager.get_connection(transfer_handle.peer) as connection:
            handshake = WireData(
                header=header,
                transfer_id=extras.pop("transfer_id", transfer_handle.id),
                peer_id=extras.pop("peer_id", self.this_peer_id),
                **extras,
            )
            await net.WireIO.send_msg(connection, handshake)
            self._set_transfer_socket_options(connection)
            yield connection

    @staticmethod
    def _set_transfer_socket_options(connection):
        with suppress(OSError, AttributeError):
            connection.socket.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 0)

    async def _accept_or_attach(
          self,
          event: ConnectionEvent,
          transfer_id: str,
    ) -> tuple[AbstractTransferHandle | None, bool]:
        _logger.info(f"transfer connection arrived transfer_id={transfer_id}")

        if transfer_handle := self.transfers_book.get_running(
              transfer_id,
        ):
            _logger.debug(f"attaching to existing transfer, {transfer_handle=}")
            transfer_handle.connection_made(event.connection)
            return transfer_handle, True

        accepted = await self.transfer_consenter.respond_to_incoming_transfer(
            event.connection, event.handshake.peer_id
        )

        if not accepted:
            return None, True

        return None, False

    async def _run_receiver(
          self,
          event: ConnectionEvent,
          transfer_id: str,
          handle_factory: Callable[[RemotePeer, str], Awaitable[AbstractTransferHandle]],
          kind: TransferKind,
    ):
        receiver_handle = None
        try:
            receiver_handle = await handle_factory(event.connection.peer, transfer_id)  # TODO: handle errors
            self._add_current(receiver_handle, kind)
            await self._run_transfer(
                receiver_handle.status_updater,
                receiver_handle,
                event.connection,
            )
        except TransferIncomplete as exp:
            if receiver_handle:
                await self.transfer_events.transfer_incomplete(receiver_handle, exp)
        finally:
            if receiver_handle:
                await self._finalize(receiver_handle)
                with suppress(Exception):
                    await receiver_handle.status_updater.close()

    async def _run_transfer(
          self,
          status_iter,
          transfer_handle: AbstractTransferHandle,
          *connections,
    ):
        await self.transfer_events.transfer_started(transfer_handle)
        async with transfer_handle, aclosing(transfer_handle.start_transfer()) as loop:
            for connection in connections:
                transfer_handle.connection_made(connection)

            async for _ in loop:
                if status_iter.should_yield():
                    await self.transfer_events.transfer_update(transfer_handle)

    async def _make_file_receiver(self, peer: RemotePeer, transfer_id: str):
        status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
        return files.Receiver(
            peer,
            transfer_id,
            self.default_download_path,
            status_updater,
        )

    async def _make_directory_receiver(
          self,
          peer: RemotePeer,
          transfer_id: str,
          dir_path: Path,
    ):
        status_updater = StatusMixIn(const.TRANSFER_STATUS_UPDATE_FREQ)
        return files.DirReceiver(
            peer,
            transfer_id,
            files.rename_directory_with_increment(self.default_download_path, dir_path),
            status_updater,
        )

    async def _make_big_file_receiver(
          self,
          peer: RemotePeer,
          transfer_id: str,
          main_file: FileItem,
    ):
        status_updater = StatusIterator(const.TRANSFER_STATUS_UPDATE_FREQ)
        receiver = files.BigFileReceiver(
            peer,
            transfer_id,
            self.default_download_path,
            status_updater,
        )
        receiver.current_transfer = main_file
        return receiver

    def _add_current(
          self,
          transfer_handle: AbstractTransferHandle,
          kind: TransferKind,
    ):
        self.transfers_book.add(
            transfer_handle,
            kind,
        )

    async def _finalize(self, transfer_handle: AbstractTransferHandle):
        _logger.debug(f"finalizing transfer={transfer_handle!r}")

        if transfer_handle.state in (TransferState.COMPLETED, TransferState.ABORTING):
            self.transfers_book.move(transfer_handle.id, TransferBookBucket.COMPLETED)
            if transfer_handle.state is TransferState.COMPLETED:
                await self.transfer_events.transfer_completed(transfer_handle)
        elif transfer_handle.state in (TransferState.PAUSED, TransferState.CONNECTING):
            self.transfers_book.move(transfer_handle.id, TransferBookBucket.SCHEDULED)
