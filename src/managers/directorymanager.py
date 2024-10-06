import asyncio

from src.avails import WireData, dialogs


async def open_dir_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, dialogs.Dialog.open_directory_dialog_window)
    await result

    return result.result()


def new_directory_transfer_request(request_packet: WireData):
    ...
