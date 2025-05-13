import asyncio
from pathlib import Path

from src.avails import BaseDispatcher, DataWeaver, RemotePeer
from src.avails.exceptions import FailedToSend, RemotePeerNotFound
from src.conduit import logger, webpage
from src.conduit.headers import HANDLE
from src.core import peers
from src.managers import directorymanager, filemanager, message


class FrontEndDataDispatcher(BaseDispatcher):
    __slots__ = ()

    async def submit(self, data_weaver):
        try:
            await self.registry[data_weaver.header](data_weaver)
        except Exception as exp:
            logger.error("data dispatcher failed with", exc_info=exp)

    def register_all(self):
        self.registry.update(
            {
                HANDLE.SEND_DIR: new_dir_transfer,
                HANDLE.SEND_FILE: send_file,
                HANDLE.SEND_TEXT: send_text,
                HANDLE.SEND_BIGFILE: send_big_file,
                HANDLE.SEND_FILE_TO_MULTIPLE_PEERS: send_files_to_multiple_peers,
                HANDLE.CONNECT_USER: connect_user
            }
        )


async def connect_user(data: DataWeaver):
    if await message.connect_ahead(data.peer_id):
        await webpage.peer_connected(data.peer_id)
    else:
        await webpage.failed_to_reach(data.peer_id)


async def send_text(command_data: DataWeaver):
    peer_id = command_data.peer_id
    if isinstance(peer_id, list):
        peer_id = peer_id[0]
    try:
        return await message.send_message(command_data.content, peer_id)
    except FailedToSend as fts:
        await webpage.failed_to_send_message(fts.item.msg_id, peer_id)


async def new_dir_transfer(command_data: DataWeaver):
    if p := command_data.content['path']:
        dir_path = p
    else:
        dir_path = await directorymanager.open_dir_selector()

    if not dir_path:
        return

    peer_id = command_data.peer_id
    remote_peer = await peers.get_remote_peer(peer_id)
    if not remote_peer:
        raise Exception(f"cannot find remote peer object for given id{peer_id}")

    await directorymanager.send_directory(remote_peer, dir_path)


async def _get_file_paths(command_data: DataWeaver):
    if "paths" in command_data:
        selected_files = [Path(x) for x in command_data["paths"]]
    else:
        selected_files = await filemanager.open_file_selector()
        if not selected_files:
            return
    return list(map(Path, selected_files))


async def send_file(command_data: DataWeaver):
    selected_files = await _get_file_paths(command_data)
    if not any(selected_files):
        return

    try:
        peer = await peers.get_remote_peer(command_data.peer_id)
    except RemotePeerNotFound:
        await webpage.failed_to_reach(command_data.peer_id)
        return

    await filemanager.send_files_to_peer(peer, selected_files)


async def send_big_file(command_data: DataWeaver):
    selected_files = await _get_file_paths(command_data)
    if not any(selected_files):
        return

    peer = await peers.get_remote_peer(command_data.peer_id)
    if peer is None:
        await webpage.failed_to_reach(command_data.peer_id)
        return

    await filemanager.send_big_file(peer, selected_files)


async def send_files_to_multiple_peers(command_data: DataWeaver):
    selected_files = await _get_file_paths(command_data)
    if not any(selected_files):
        return

    peer_ids = command_data.content["peerList"]
    peer_objs = await asyncio.gather(*((peers.get_remote_peer(peer_id)) for peer_id in peer_ids),
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
    file_sender = filemanager.start_new_otm_file_transfer(selected_files, success_peers)

    async for update in file_sender.start():
        print(update)
        # TODO: feed updates to frontend
