from pathlib import Path
from sys import stderr

from src.avails import DataWeaver, use
from src.core.transfers import HEADERS
from src.managers import filemanager


async def send_a_directory(command_data: DataWeaver):
    ...


async def send_file_to_peer(command_data: DataWeaver):
    selected_files = await filemanager.open_file_selector()
    if selected_files:
        print(selected_files)
        selected_files = [Path(x) for x in selected_files]
        peer_id = command_data.content['peer_id']
        file_sender = filemanager.FileSender(selected_files, peer_id)
        await file_sender.send_files()


async def send_text(command_data: DataWeaver):
    ...


async def send_file_to_multiple_peers(command_data: DataWeaver):
    ...


async def send_dir_to_multiple_peers(command_data: DataWeaver):
    ...


function_dict = {
    HEADERS.HANDLE_SEND_DIR: send_a_directory,
    HEADERS.HANDLE_SEND_FILE: send_file_to_peer,
    HEADERS.HANDLE_SEND_TEXT: send_text,
    HEADERS.HANDLE_SEND_FILE_TO_MULTIPLE_PEERS: send_file_to_multiple_peers,
    HEADERS.HANDLE_SEND_DIR_TO_MULTIPLE_PEERS: send_dir_to_multiple_peers,
}


async def handler(data: str):
    print("handlesignals handler", data)
    func = handler
    try:
        data = DataWeaver(serial_data=data)
        func = function_dict[data.header]
        await func(data)
    except Exception as exp:
        print(f"Got an exception at handledata - {use.func_str(func)}", exp, file=stderr)
        raise
