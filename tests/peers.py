import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.append("C:\\Users\\7862s\\Desktop\\PeerConnect\\")

from src.managers.statemanager import State
from test import initiate, test_initial_states
from src.core import peers
from src.avails import const


async def test_list_of_peers():
    while True:
        await asyncio.get_event_loop().run_in_executor(ThreadPoolExecutor(), func=lambda: input("enter"))
        peer_list = await peers.get_more_peers()
        print(peer_list)

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    i_states = test_initial_states()
    s8 = State("checking for peer gathering", test_list_of_peers, is_blocking=True)
    asyncio.run(initiate(i_states + (s8,)), debug=True)
