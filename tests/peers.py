import asyncio
import os

import _path  # noqa
from src.avails import const
from src.avails.useables import async_input
from src.core import Dock, peers
from src.managers.statemanager import State
from test import initiate, test_initial_states


async def test_list_of_peers():
    while True:
        await async_input("ENTER")
        peer_list = await peers.get_more_peers()
        print(peer_list)


async def test_members():
    await asyncio.sleep(2)
    print("[INFO] members:", Dock.peer_list)


if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    i_states = test_initial_states()
    members_test = State("testing members", test_members)
    peer_gathers = State("checking for peer gathering", test_list_of_peers, is_blocking=True)

    asyncio.run(initiate(i_states + (members_test, peer_gathers)), debug=True)
