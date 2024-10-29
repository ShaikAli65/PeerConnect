from src.avails import DataWeaver
from src.core import Dock
from src.core.transfers import HEADERS
from src.core.webpage_handlers import handledata


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
            header=HEADERS.HANDLE_SEND_FILE_TO_MULTIPLE_PEERS,
            content={
                'peer_list': [x for x in Dock.peer_list.keys()],
            },
            _id=p.id,
        )
        await handledata.send_file_to_multiple_peers(command_data)

    except StopIteration:
        print("no peers available")
