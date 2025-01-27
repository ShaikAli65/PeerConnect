import asyncio

import _path  # noqa
from src.avails import DataWeaver
from src.managers.statemanager import State
from src.webpage_handlers import handledata
from test import get_a_peer
from tests.test import start_test


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
    s10 = State("test dir transfer", test_dir_transfer, is_blocking=True)
    start_test([s10])
