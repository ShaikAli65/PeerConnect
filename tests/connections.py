import asyncio
import random
import traceback
from contextlib import AsyncExitStack

import _path  # noqa
from src.avails import WireData, const
from src.avails.events import MessageEvent
from src.avails.exceptions import ResourceBusy
from src.core.bandwidth import Watcher
from src.core.connector import Connector
from src.core.public import Dock, get_this_remote_peer, msg_dispatcher
from src.managers import message
from src.managers.statemanager import State
from src.transfers import HEADERS
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
    assert peer is not None, "[TEST][FAILED] no peers test "

    connector = Connector()
    const.MAX_CONNECTIONS_BETWEEN_PEERS = 3
    available_after = None
    connections = set()

    async def connection_wait_task(connection_wait):
        async with connection_wait:
            return await connection_wait.wait()

    async with AsyncExitStack() as a_exit:
        for _ in range(const.MAX_CONNECTIONS_BETWEEN_PEERS):
            c = await a_exit.enter_async_context(connector.connect(peer))
            connections.add(c)

        try:
            await a_exit.enter_async_context(connector.connect(peer, raise_if_busy=True))
            print("[TEST][FAILED] no exception found, connection limit test ")
        except ResourceBusy as rb:
            available_after = rb.available_after
            connection_wait_t = asyncio.create_task(connection_wait_task(available_after))
            print(f"[TEST][PASSED] connection limit test  {rb=}")

    assert available_after is not None, "[TEST][FAILED] no exception found, test "

    try:
        await asyncio.wait_for(connection_wait_t, 0)
        print("[TEST][PASSED] 'available after' condition test ", available_after)
    except TimeoutError:
        print("[TEST][FAILED] 'available after' condition check ", available_after)

    async with connector.connect(peer) as connection:
        pass

    assert connection in connections, "[TEST][FAILED] connection not found in the expected set"

    print("[TEST][PASSED] connection found in the expected set, test ")


async def test_message():
    peer = get_a_peer()
    assert peer is not None

    check = asyncio.Event()

    ping = WireData(
        header=HEADERS.PING,
        peer_id=get_this_remote_peer().peer_id,
        msg_id=(ping_id := str(random.randint(1, 1000)))
    )

    def UNPingHandlerMock():
        async def handler(msg_event: MessageEvent):
            if msg_event.msg.msg_id == ping_id:
                check.set()
                print("ping received")

        return handler

    msg_dispatcher().register_handler(HEADERS.UNPING, UNPingHandlerMock())

    async with message.get_msg_conn(peer) as connection:
        await connection.send(ping)

    try:
        await asyncio.wait_for(check.wait(), 3)
    except TimeoutError:
        print("[TEST][FAILED] to send message reason: un ping not received")
    else:
        msg_dispatcher().remove_handler(HEADERS.UNPING)
        print("[TEST][PASSED]  message")


async def test_connections():
    print("waiting to get into network")
    await Dock.in_network.wait()

    print("starting testing connections")
    try:
        await test_connection()
        await test_connection_pool()
        await test_message()
    except Exception:
        print("#@" * 23)  # debug
        traceback.print_exc()
        raise


if __name__ == "__main__":
    s1 = State("testing connection", test_connections, is_blocking=True)

    start_test1((), (s1,))
