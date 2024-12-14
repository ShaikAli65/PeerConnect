import asyncio

from src.avails import WireData, get_dialog_handler


async def open_dir_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, get_dialog_handler().open_directory_dialog_window)
    await result

    return result.result()


def new_directory_transfer_request(request_packet: WireData):
    ...
