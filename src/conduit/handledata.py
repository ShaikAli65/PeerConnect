import traceback
from pathlib import Path

from src.avails import BaseDispatcher, DataWeaver, WireData, const
from src.conduit import logger
from src.conduit.headers import HANDLE
from src.core import peers
from src.core.public import Dock, get_this_remote_peer
from src.managers import directorymanager, filemanager, message
from src.transfers import HEADERS


class FrontEndDataDispatcher(BaseDispatcher):
    __slots__ = ()

    async def submit(self, data_weaver):
        try:
            await self.registry[data_weaver.header](data_weaver)
        except Exception as exp:
            logger.error("data dispatcher", exc_info=exp)

    def register_all(self):
        self.registry.update(
            {
                HANDLE.SEND_DIR: new_dir_transfer,
                HANDLE.SEND_FILE: send_file,
                HANDLE.SEND_TEXT: send_text,
                HANDLE.SEND_FILE_TO_MULTIPLE_PEERS: send_files_to_multiple_peers,
                HANDLE.SEND_DIR_TO_MULTIPLE_PEERS: send_dir_to_multiple_peers,
            }
        )


async def new_dir_transfer(command_data: DataWeaver):
    if p := command_data.content['path']:
        dir_path = p
    else:
        dir_path = await directorymanager.open_dir_selector()

    if not dir_path:
        return

    peer_id = command_data.peer_id
    remote_peer = await peers.get_remote_peer_at_every_cost(peer_id)
    if not remote_peer:
        raise Exception(f"cannot find remote peer object for given id{peer_id}")

    await directorymanager.send_directory(remote_peer, dir_path)


async def send_file(command_data: DataWeaver):
    if "paths" in command_data:
        selected_files = [Path(x) for x in command_data["paths"]]
    else:
        selected_files = await filemanager.open_file_selector()
        if not selected_files:
            return

    selected_files = [Path(x) for x in selected_files]
    send_files = filemanager.send_files_to_peer(command_data.peer_id, selected_files)
    try:
        async with send_files as sender:
            print(sender)  # debug
    except OSError as e:
        if const.debug:
            traceback.print_exc()
            print("{error}", e)  # debug
        # page_handle.dispatch_data(DataWeaver)


async def send_text(command_data: DataWeaver):
    peer_obj = await peers.get_remote_peer_at_every_cost(command_data.peer_id)
    if peer_obj is None:
        return  # send data to page that peer is not reachable

    async with message.get_msg_conn(peer_obj) as conn:
        data = WireData(
            header=HEADERS.CMD_TEXT,
            msg_id=get_this_remote_peer().peer_id,
            message=command_data.content,
        )
        # TODO: wrap around with try except, signal page status update
        await conn.send(bytes(data))


async def send_files_to_multiple_peers(command_data: DataWeaver):
    selected_files = await filemanager.open_file_selector()
    if not selected_files:
        return
    peer_ids = command_data.content["peerList"]
    peer_objects = [Dock.peer_list.get_peer(peer_id) for peer_id in peer_ids]
    selected_files = [Path(x) for x in selected_files]
    file_sender = filemanager.start_new_otm_file_transfer(selected_files, peer_objects)

    async for update in file_sender.start():
        print(update)
        # TODO: feed updates to frontend


async def send_dir_to_multiple_peers(_: DataWeaver): ...
