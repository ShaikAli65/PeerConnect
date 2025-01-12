import asyncio
import os

import _path  # noqa
from src.avails import DataWeaver, const
from src.core import transfers
from src.core.webpage_handlers import handledata
from src.managers.statemanager import State
from test import initiate, test_initial_states
from tests.test import get_a_peer


async def test_file_transfer():
    await asyncio.sleep(2)
    if p := get_a_peer():
        data = DataWeaver(
            header=transfers.HANDLE.SEND_FILE,
            peer_id=p.peer_id,
        )
        try:
            await handledata.send_file(data)
        except Exception as e:
            print(e)


if __name__ == '__main__':
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    i_states = test_initial_states()
    s10 = State("test file transfer", test_file_transfer, is_blocking=True)

    asyncio.run(initiate(i_states + (s10,)), debug=True)
