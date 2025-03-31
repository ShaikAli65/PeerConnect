import asyncio
import traceback
from contextlib import AsyncExitStack

import _path  # noqa
from src.avails import const
from src.avails.exceptions import ResourceBusy
from src.core.app import provide_app_ctx
from src.core.bandwidth import Watcher
from src.core.connector import Connector
from src.managers.statemanager import State
from tests.test import get_a_peer, start_test1


async def test_connection():
    peer = get_a_peer()
    assert peer is not None, "no peers"
    connector = Connector()

    async with connector.connect(peer) as connection:
        watcher = Watcher()
        active, closed = await watcher.refresh(peer, connection)

        assert connection in active, "connection is not active"

    print("[TEST][PASSED] connected")


async def test_connection_pool():
    peer = get_a_peer()
    assert peer is not None, "[TEST][FAILED] no peers test"

    connector = Connector()
    const.MAX_CONNECTIONS_BETWEEN_PEERS = 3
    available_after = None
    connections = set()

    async def connection_wait_task(connection_wait):
        async with connection_wait:
            await connection_wait.wait_for(connector.is_connection_available(peer))
            print("[TEST][INFO] connection limit released")

    async with AsyncExitStack() as a_exit:
        for _ in range(const.MAX_CONNECTIONS_BETWEEN_PEERS):
            c = await a_exit.enter_async_context(connector.connect(peer))
            connections.add(c)

        try:
            await a_exit.enter_async_context(connector.connect(peer, raise_if_busy=True))
            print("[TEST][FAILED] connection limiting, no exception found")
        except ResourceBusy as rb:
            available_after = rb.available_after
            connection_wait_t = asyncio.create_task(connection_wait_task(available_after))
            print(f"[TEST][PASSED] connection limit test  {rb=}")

    assert available_after is not None, "[TEST][FAILED] no exception found, test "

    try:
        await asyncio.wait_for(connection_wait_t, 1)
        print("[TEST][PASSED] 'available after' condition test ", available_after)
    except TimeoutError:
        print("[TEST][FAILED] 'available after' condition check ", available_after)

    async with connector.connect(peer) as connection:
        pass

    assert connection in connections, "[TEST][FAILED] connection not found in the expected set"

    print("[TEST][PASSED] connection found in the expected set")


@provide_app_ctx
async def test_connections(app_ctx):
    print("waiting to get into network")
    await app_ctx.in_network.wait()

    print("starting testing connections")
    try:
        await test_connection()
        await test_connection_pool()
    except Exception:
        print("#@" * 23)  # debug
        traceback.print_exc()
        raise


if __name__ == "__main__":
    s1 = State("testing connection", test_connections, is_blocking=True)

    start_test1((), (s1,))
