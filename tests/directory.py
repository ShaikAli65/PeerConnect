import asyncio
import os

import _path  # noqa
from src.avails import const
from src.managers.directorymanager import new_directory_send_transfer
from src.managers.statemanager import State
from test import get_a_peer, initiate, test_initial_states


async def test_dir_transfer():
    await asyncio.sleep(2)
    if p := get_a_peer():
        await new_directory_send_transfer(p.peer_id)


if __name__ == '__main__':
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    i_states = test_initial_states()
    s10 = State("test dir transfer", test_dir_transfer, is_blocking=True)
    asyncio.run(initiate(i_states + (s10,)), debug=True)
