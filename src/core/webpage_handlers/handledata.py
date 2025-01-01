from pathlib import Path
from sys import stderr

from src.avails import DataWeaver, Wire, WireData, use
from src.core import Dock, get_this_remote_peer, peers
from src.core.connections import Connector
from src.core.transfers import HEADERS
from src.managers import filemanager
from src.managers.filemanager import send_files_to_peer


async def send_a_directory(command_data: DataWeaver): ...


async def send_file_to_peer(command_data: DataWeaver):
    selected_files = await filemanager.open_file_selector()
    if selected_files:
        # print(selected_files)
        selected_files = [Path(x) for x in selected_files]
        peer_id = command_data.content["peer_id"]

        await send_files_to_peer(peer_id, selected_files)


async def send_text(command_data: DataWeaver):
    peer_id = command_data.content["peer_id"]
    peer_obj = await peers.get_remote_peer_at_every_cost(peer_id)

    if peer_obj is None:
        return  # send data to page that peer is not reachable

    connection = await Connector.get_connection(peer_obj)
    data = WireData(
        header=HEADERS.CMD_TEXT,
        _id=get_this_remote_peer().id,
        message=command_data.content,
    )
    # :todo: wrap around with try except, signal page status update
    await Wire.send_async(connection, bytes(data))


async def send_file_to_multiple_peers(command_data: DataWeaver):
    peer_ids = command_data.content["peer_list"]
    peer_objects = [Dock.peer_list.get_peer(peer_id) for peer_id in peer_ids]
    selected_files = await filemanager.open_file_selector()
    if not selected_files:
        return
    selected_files = [Path(x) for x in selected_files]
    file_sender = filemanager.start_new_otm_file_transfer(selected_files, peer_objects)
    async for update in file_sender.start():
        print(update)
        # :todo: feed updates to frontend


async def send_dir_to_multiple_peers(command_data: DataWeaver): ...


function_dict = {
    HEADERS.HANDLE_SEND_DIR: send_a_directory,
    HEADERS.HANDLE_SEND_FILE: send_file_to_peer,
    HEADERS.HANDLE_SEND_TEXT: send_text,
    HEADERS.HANDLE_SEND_FILE_TO_MULTIPLE_PEERS: send_file_to_multiple_peers,
    HEADERS.HANDLE_SEND_DIR_TO_MULTIPLE_PEERS: send_dir_to_multiple_peers,
}


async def handler(data: DataWeaver):
    print("handlesignals handler", data)
    func = handler
    try:
        func = function_dict[data.header]
        await func(data)
    except Exception as exp:
        print(
            f"Got an exception at handledata - {use.func_str(func)}", exp, file=stderr
        )
        raise
