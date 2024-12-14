import asyncio
import os
import sys
sys.path.append("C:\\Users\\7862s\\Desktop\\PeerConnect\\")

from src.managers.statemanager import State
from test import initiate, test_initial_states
from src.avails import DataWeaver
from src.core import transfers
from src.core.webpage_handlers import handledata
from src.avails import const
from src.core import Dock


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

if __name__ == '__main__':
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    i_states = test_initial_states()
    s10 = State("test file transfer", test_file_transfer, is_blocking=True)

    asyncio.run(initiate(i_states + (s10,)), debug=True)
