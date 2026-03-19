import logging

import _path  # noqa
from src.avails.useables import async_input
from src.core import peers
from tests.test import start_test

_logger = logging.getLogger(__name__)


async def test_list_of_peers():
    while True:
        await async_input("ENTER")
        peer_list = await peers.get_more_peers()
        print(peer_list)


@provide_app_ctx
async def test_members(app_ctx=None):
    await app_ctx.in_network.wait()
    assert len(app_ctx.peer_list) > 0, "expected some members in peer_list after entering into network"
    _logger.info("[TEST PASSED] found peers")
    print("[INFO] members:", app_ctx.peer_list)


if __name__ == "__main__":
    members_test = State("testing members", test_members)
    peer_gathers = State("checking for peer gathering", test_list_of_peers, is_blocking=True)
    start_test(members_test, peer_gathers)
