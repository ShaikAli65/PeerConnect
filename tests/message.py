import asyncio
import os

import _path  # noqa
from src.avails import DataWeaver, RemotePeer, const
from src.avails.useables import async_input
from src.core import Dock
from src.core.transfers import HANDLE
from test import initiate, test_initial_states


async def test_message():
    message = await async_input()
    Dock.peer_list.add_peer(peer_obj=RemotePeer(
        peer_id=B'',
    ))
    DataWeaver(
        header=HANDLE.SEND_TEXT,

    )


if __name__ == '__main__':
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    initial_states = test_initial_states()
    states = initial_states + ()

    asyncio.run(initiate(states), debug=True)
