import asyncio
import os

import _path  # noqa
from src.avails import DataWeaver, const
from src.core import Dock
from src.managers.statemanager import State
from src.webpage_handlers import handledata
from src.webpage_handlers.headers import HANDLE
from test import initiate, test_initial_states


async def test_one_to_many_file_transfer():
    # await async_input()
    """
    Last test results:

    Configured parameters:
    session
        fanout : 5 no.
        file_count  : 3 no.
        timeout : 3 sec
    chunk_size : 262144 bytes
    node count : 10

    Observed tree:
|==={4}
    |+++{8}
        |+++{9}
            |---{2}
            |+++{3}
                 |---{7}
        |+++{13}
            |---{3}
    |+++{2}
        |---{9}
        |---{5}
        |---{7}
    |+++{11}
        |+++{7}
             |---{3}
        |---{13}
        |---{1}
    |+++{10}
        |+++{1}.
        |+++{5}

    Expected:
    Best tree should have a maxmimum depth of 0 - 1 - 2.

    Possible cause:
    using hyper cube in initial graph formation

    """
    try:
        p = next(iter(Dock.peer_list))
        command_data = DataWeaver(
            header=HANDLE.SEND_FILE_TO_MULTIPLE_PEERS,
            content={
                'peer_list': [x for x in Dock.peer_list.keys()],
            },
            peer_id=p.peer_id,
        )
        await handledata.send_files_to_multiple_peers(command_data)

    except StopIteration:
        print("no peers available")


if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    const.debug = False
    i_states = test_initial_states()
    s11 = State("test otm file transfer", test_one_to_many_file_transfer, is_blocking=True)

    asyncio.run(initiate(i_states + (s11,)), debug=True)
