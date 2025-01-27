import asyncio

import _path  # noqa
import src.webpage_handlers
import src.webpage_handlers.headers
from src.avails import DataWeaver
from src.managers.statemanager import State
from src.webpage_handlers import handledata
from test import test_initial_states
from tests.test import get_a_peer, start_test


async def test_file_transfer():
    await asyncio.sleep(2)
    if p := get_a_peer():
        data = DataWeaver(
            header=src.webpage_handlers.headers.HANDLE.SEND_FILE,
            peer_id=p.peer_id,
        )
        try:
            await handledata.send_file(data)
        except Exception as e:
            print(e)


if __name__ == '__main__':
    i_states = test_initial_states()
    s10 = State("test file transfer", test_file_transfer, is_blocking=True)
    start_test([s10])
