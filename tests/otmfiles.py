from src.avails import DataWeaver
from src.core import Dock
from src.core.transfers import HEADERS
from src.core.webpage_handlers import handledata


async def test_one_to_many_file_transfer():

    # await async_input()
    try:
        p = next(iter(Dock.peer_list))
        command_data = DataWeaver(
            header=HEADERS.HANDLE_SEND_FILE_TO_MULTIPLE_PEERS,
            content={
                'peer_list': [x for x in Dock.peer_list.keys()],
            },
            _id=p.id,
        )
        await handledata.send_file_to_multiple_peers(command_data)

    except StopIteration:
        print("no peers available")
