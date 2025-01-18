import asyncio
import os

import _path  # noqa
from src.avails import DataWeaver, const
from src.managers.statemanager import State
from src.webpage_handlers import handledata
from test import get_a_peer, initiate, test_initial_states


async def test_dir_transfer():
    await asyncio.sleep(3)
    if p := get_a_peer():
        await handledata.new_dir_transfer(
            DataWeaver(
                peer_id=p.peer_id,
                content={
                    'path':"C:/Users/7862s/Desktop/statemachines",
                }
            )
        )


if __name__ == '__main__':
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    i_states = test_initial_states()
    s10 = State("test dir transfer", test_dir_transfer, is_blocking=True)
    asyncio.run(initiate(i_states + (s10,)), debug=True)
