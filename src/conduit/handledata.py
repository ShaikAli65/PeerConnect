import asyncio
from pathlib import Path

from conduit import ui_events
from conduit.bases import FrontEnd, UIError
from src.avails import RemotePeer
from src.avails.exceptions import FailedToSend, RemotePeerNotFound
from src.conduit import logger, webpage
from src.conduit.dialogs import get_dialog_handler
from src.conduit.ui_codec import DataWeaver


def handlers_to_register(
      peer_service,
      msg_conn_service,
      transfer_manager,
      web_frontend,
):
    return [
        (ui_events.SendText, SendTextHandler(peer_service, msg_conn_service, web_frontend)),
        (ui_events.SendDirectory, SendDirHandler(peer_service, transfer_manager, web_frontend)),
        (ui_events.SendFiles, SendFileHandler(peer_service, transfer_manager, web_frontend)),
        (ui_events.SendBigFile, SendBigFileHandler(peer_service, transfer_manager)),
        (ui_events.SendFilesToMultiplePeers, SendFileToMultiplePeersHandler(peer_service)),
        (ui_events.SendDirectoryToMultiplePeers, SendDirectoryToMultiplePeersHandler),
    ]


def SendTextHandler(
      peer_service,
      messaging_service,
      frontend,
):
    async def send_text(send_txt_event: ui_events.SendText):
        try:
            peer = await peer_service.get_remote_peer(send_txt_event.peer_id)
            await messaging_service.send_message(send_txt_event.text, peer)
        except FailedToSend as fts:
            # TODO: does failed to send contain item and item.msg_id
            frontend.send_error(ui_events.MessageSendFailed(send_txt_event.peer_id, fts.item.msg_id))

    return send_text


def SendDirHandler(
      peer_service,
      transfer_manager,
      frontend,
):
    async def new_dir_transfer(event: ui_events.SendDirectory):
        if not (dir_path := await _get_file_paths(event, prompter=open_directory_selector)):
            return
        try:
            peer = await peer_service.get_remote_peer(event.peer_id)
        except RemotePeerNotFound:  # TODO: this is a bit of a hack, should be handled in the UI
            await frontend.send_error(ui_events.UIError())
            return

        logger.info(f"starting new directory transfer {event}")
        await transfer_manager.send_directory(peer, dir_path[0])
        logger.info(f"sent directory {dir_path[0]} to {peer}")

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
      peer_service,
      transfer_manager,
      frontend,
):
    async def send_file(command_data: ui_events.SendFiles):
        if not any(selected_files := await _get_file_paths(command_data, prompter=open_file_selector)):
            return

        peer = await peer_service.get_remote_peer(command_data.peer_id)
        await transfer_manager.send_files(peer, selected_files, )

        logger.info(
            f"sent file to {peer} with {len(selected_files)} files"
        )

    return send_file


def SendBigFileHandler(
      peer_service,
      transfer_manager,
):
    async def send_big_file(send_file_command: ui_events.SendBigFile):
        if not any(
              selected_files := await _get_file_paths(send_file_command.paths, prompter=open_file_selector)):
            return

        peer = await peer_service.get_remote_peer(send_file_command.peer_id)
        for file in selected_files:
            await transfer_manager.send_big_file(peer, file)
            logger.info(f"sent big file {file} to {peer}")

    return send_big_file


def SendFileToMultiplePeersHandler(
      peer_service,
      transfer_manager,
      frontend,
):
    async def send_files_to_multiple_peers(event: ui_events.SendFilesToMultiplePeers):
        if not any(selected_files := await _get_file_paths(event, prompter=open_file_selector)):
            # TODO: may be we need a no file selected event, so frontend can handle it in all of the functions here
            return

        peer_objs = await asyncio.gather(*((peer_service.get_remote_peer(peer_id)) for peer_id in event.peer_ids),
                                         return_exceptions=True)
        success_peers, failed = [], []

        for peer in peer_objs:
            if isinstance(peer, RemotePeer):
                success_peers.append(peer)
            if isinstance(peer, RemotePeerNotFound):
                failed.append(peer.peer_id)

        for peer_id in failed:
            await frontend.send_error(UIError())  # TODO: handle this better

        if not success_peers:
            return

        selected_files = [Path(x) for x in selected_files]
        file_sender = transfer_manager.start_new_otm_file_transfer(
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
