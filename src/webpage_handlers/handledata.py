import asyncio
import traceback
from pathlib import Path

from src.avails import BaseDispatcher, DataWeaver, Wire, WireData, get_dialog_handler
from src.core import Dock, get_this_remote_peer, peers
from src.core.connections import Connector
from src.managers import directorymanager, filemanager
from src.managers.directorymanager import send_directory
from src.transfers import HEADERS
from src.webpage_handlers import logger
from src.webpage_handlers.headers import HANDLE


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

    await send_directory(remote_peer, dir_path)


async def send_file(command_data: DataWeaver):
    selected_files = await open_file_selector()
    if not selected_files:
        return

    selected_files = [Path(x) for x in selected_files]
    send_files = filemanager.send_files_to_peer(command_data.peer_id, selected_files)
    try:
        async with send_files as sender:
            print(sender)
    except OSError as e:
        traceback.print_exc()
        print("{eror}", e)
        # pagehandle.dispatch_data(DataWeaver)


async def send_text(command_data: DataWeaver):
    peer_obj = await peers.get_remote_peer_at_every_cost(command_data.peer_id)

    if peer_obj is None:
        return  # send data to page that peer is not reachable

    connection = await Connector.get_connection(peer_obj)
    data = WireData(
        header=HEADERS.CMD_TEXT,
        msg_id=get_this_remote_peer().peer_id,
        message=command_data.content,
    )
    # :todo: wrap around with try except, signal page status update
    await Wire.send_async(connection, bytes(data))


async def send_files_to_multiple_peers(command_data: DataWeaver):
    selected_files = await open_file_selector()
    if not selected_files:
        return
    peer_ids = command_data.content["peerList"]
    peer_objects = [Dock.peer_list.get_peer(peer_id) for peer_id in peer_ids]
    selected_files = [Path(x) for x in selected_files]
    file_sender = filemanager.start_new_otm_file_transfer(selected_files, peer_objects)

    async for update in file_sender.start():
        print(update)
        # :todo: feed updates to frontend


async def send_dir_to_multiple_peers(command_data: DataWeaver): ...


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_dialog_handler().open_file_dialog_window)  # noqa
    if any(result) and result[0] == '.':
        return []
    return result
