import asyncio
import random
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


async def test_connection_pool():

    peer = get_a_peer()
    assert peer is not None, "no peers test failed"

    connector = Connector()
    const.MAX_CONNECTIONS_BETWEEN_PEERS = 3

    connections = set()
    async with AsyncExitStack() as a_exit:
        for _ in range(const.MAX_CONNECTIONS_BETWEEN_PEERS):
            c = await a_exit.enter_async_context(connector.connect(peer))
            connections.add(c)
        try:
            await a_exit.enter_async_context(connector.connect(peer, raise_if_busy=True))
            print("no exception found, connection limit test failed")
        except ResourceBusy as rb:
            print("connection limit test passed", rb)

    async with rb.available_after:
        try:
            await asyncio.wait_for(rb.available_after.wait(), 0.001)
            print("'available after' condition test passed")
        except TimeoutError:
            print("'available after' condition check failed")

    async with connector.connect(peer) as connection:
        pass
    assert connection in connections, "connection found in the expected set, test passed"


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
        connection.send(ping)

    try:
        await asyncio.wait_for(check.wait(), 3)
    except TimeoutError:
        print("failed to send message reason: un ping not received")

    msg_dispatcher().remove_handler(HEADERS.UNPING)
    print("passed message")


async def test_connections():
    print("waiting to get into network")
    await Dock.in_network.wait()

    print("starting testing connections")
    await test_connection()
    await test_connection_pool()
    await test_message()


if __name__ == "__main__":
    s1 = State("testing connection", test_connections, is_blocking=True)

    start_test1((), (s1,))
