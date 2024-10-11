from src.avails import DataWeaver
from src.core import Dock, transfers
from src.core.webpage_handlers import handledata


async def test_file_transfer():
    try:
        p = next(iter(Dock.peer_list))
        data = DataWeaver(
            header=transfers.HEADERS.HANDLE_SEND_FILE,
            content={
                'peer_id': p.id,
            }
        )
        try:
            await handledata.send_file_to_peer(data)
        except Exception as e:
            print(e)
    except StopIteration:
        print("no peers available")
