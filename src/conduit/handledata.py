import asyncio
from pathlib import Path

from src.avails import RemotePeer
from src.avails.exceptions import FailedToSend, RemotePeerNotFound, TransferRejected
from src.conduit import logger, webpage
from src.conduit.dialogs import get_dialog_handler
from src.conduit.pagehandle import FrontEndMessagesDispatcher
from src.conduit.ui_codec import DataWeaver
from src.conduit.ui_events import MessageSendFailed, PeerPresenceChanged, PeerSummary, \
    SendBigFile, SendDirectory, \
    SendDirectoryToMultiplePeers, \
    SendFiles, \
    SendFilesToMultiplePeers, \
    SendText
from src.managers import message


def register_handlers(
      dispatcher: FrontEndMessagesDispatcher,
      this_peer,
      conn_service,
      msg_conn_service,
      peer_service,
):
    dispatcher.register_handler(
        SendDirectory.event_name(),
        SendDirHandler(this_peer, peer_service)
    )
    dispatcher.register_handler(
        SendFiles.event_name(),
        SendFileHandler(this_peer, peer_service)
    )
    dispatcher.register_handler(
        SendText.event_name(),
        SendTextHandler(
            conn_service,
            msg_conn_service,
            peer_service,
        ))
    dispatcher.register_handler(
        SendBigFile.event_name(),
        SendBigFileHandler(this_peer, peer_service)
    )
    dispatcher.register_handler(
        SendFilesToMultiplePeers.event_name(),
        SendFileToMultiplePeersHandler(this_peer, peer_service)
    )
    dispatcher.register_handler(
        SendDirectoryToMultiplePeers.event_name(),
        SendDirectoryToMultiplePeersHandler
    )


def SendTextHandler(
      conn_service,
      msg_conn_service,
      peer_service,
      connectivity_checker,
):
    async def send_text(send_txt: SendText):
        peer_id = send_txt.peer_id
        if isinstance(peer_id, list):
            peer_id = peer_id[0]
        try:
            is_sender_present = await message.send_message(send_txt.text, peer_id)
            if not is_sender_present:
                await message.connect_and_send(
                    send_txt.text,
                    peer_id,
                    conn_service,
                    msg_conn_service,
                    peer_service,
                    connectivity_checker
                )
        except FailedToSend as fts:
            webpage.send_error(MessageSendFailed(peer_id, fts.item.msg_id))

    return send_text


def SendDirHandler(
      this_peer,
      peer_service,
      transfer_manager,
):
    async def new_dir_transfer(command_data: DataWeaver):
        if not (dir_path := await _get_file_paths(command_data, prompter=open_directory_selector)):
            return
        try:
            peer = await peer_service.get_remote_peer(command_data.peer_id)
        except RemotePeerNotFound:
            await webpage.failed_to_reach(command_data.peer_id)
            return

        logger.info(f"starting new directory transfer {command_data.content=}")
        await transfer_manager.send_directory(peer, dir_path[0], this_peer.peer_id)

    return new_dir_transfer


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_dialog_handler().open_file_dialog_window)  # noqa
    if any(result) and result[0] == '.':
        return []
    return result


async def open_directory_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, get_dialog_handler().open_directory_dialog_window)  # noqa
    return await result


async def _get_file_paths(paths, *, prompter):
    if paths:
        selected_files = [Path(x) for x in paths]
    else:
        selected_files = await prompter()
        if not selected_files:
            return ()
    return list(map(Path, selected_files))


def SendFileHandler(
      this_peer,
      peer_service,
      transfer_manager,
      frontend,
):
    async def send_file(command_data: DataWeaver):
        if not any(selected_files := await _get_file_paths(command_data, prompter=open_file_selector)):
            return

        try:
            peer = await peer_service.get_remote_peer(command_data.peer_id)
        except RemotePeerNotFound:
            await webpage.failed_to_reach(command_data.peer_id)
            return
        try:
            await transfer_manager.send_files_to_peer(
                peer,
                selected_files,
                this_peer.peer_id,
            )
        except TransferRejected:
            await frontend.transfer_confirmation(transfer_handle, False)

        logger.info(
            f"sent file to {peer} with {len(selected_files)} files"
        )

    return send_file


def SendBigFileHandler(
      this_peer,
      peer_service,
):
    async def send_big_file(send_file_command: SendBigFile):
        if not any(selected_files := await _get_file_paths(send_file_command.paths)):
            return

        peer = await peer_service.get_remote_peer(command_data.peer_id)
        if peer is None:
            webpage.notify(
                PeerPresenceChanged(PeerSummary(peer_id=command_data.peer_id, name="", ip="", online=False))
            )
            return

        await filemanager.send_big_file(
            peer,
            selected_files,
            webpage.transfer_update,
            this_peer.peer_id,
        )
        logger.info(f"sent file to {peer}")

    return send_big_file


def SendFileToMultiplePeersHandler(
      this_peer,
      peer_service,
):
    async def send_files_to_multiple_peers(command_data: DataWeaver):
        if not any(selected_files := await _get_file_paths(command_data)):
            return

        peer_ids = command_data.content["peerList"]
        peer_objs = await asyncio.gather(*((peer_service.get_remote_peer(peer_id)) for peer_id in peer_ids),
                                         return_exceptions=True)
        success_peers, failed = [], []

        for peer in peer_objs:
            if isinstance(peer, RemotePeer):
                success_peers.append(peer)
            if isinstance(peer, RemotePeerNotFound):
                failed.append(peer.peer_id)

        for peer_id in failed:
            await webpage.failed_to_reach(peer_id)

        if not success_peers:
            return

        selected_files = [Path(x) for x in selected_files]
        file_sender = filemanager.start_new_otm_file_transfer(
            selected_files,
            success_peers,
            this_peer.peer_id
        )

        async for update in file_sender.start():
            print(update)
            # TODO: feed updates to frontend

    return send_files_to_multiple_peers


def SendDirectoryToMultiplePeersHandler():
    ...
