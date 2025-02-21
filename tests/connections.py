import asyncio
import random

from src.avails import DataWeaver, Wire, WireData
from src.avails.events import ConnectionEvent, MessageEvent
from src.core import connections_dispatcher, get_this_remote_peer, msg_dispatcher
from src.core.bandwidth import Watcher
from src.core.connector import Connector
from src.managers import message
from src.managers.statemanager import State
from src.transfers import HEADERS
from tests.test import get_a_peer, start_test


async def test_connection():
    peer = get_a_peer()
    connector = Connector()

    TEST_HEADER = "TEST HEADER"

    check_handshake = WireData(
        header=TEST_HEADER,
        peer_id=get_this_remote_peer().peer_id,
        msg_id=str(random.randint(1, 1000)),
    )

    async def test_connection_handler(connection_event: ConnectionEvent):
        if connection_event.handshake.msg_id == check_handshake.peer_id:
            print("test passed")

    connections_dispatcher().register_handler(TEST_HEADER, test_connection_handler)

    async with connector.connect(peer) as connection:
        watcher = Watcher()
        active, closed = await watcher.refresh(peer, connection)

        assert connection in active, "connection is not active"

        await Wire.send_msg(connection, check_handshake)


async def test_message():
    peer = get_a_peer()
    assert peer is not None

    check = asyncio.Event()

    ping = DataWeaver(
        header=HEADERS.PING,
        peer_id=get_this_remote_peer().peer_id,
        msg_id=(ping_id := str(random.randint(1, 1000)))
    )

    async def PingHandlerMock():
        async def handler(msg_event: MessageEvent):
            if msg_event.msg.msg_id == ping_id:
                check.set()
                print("ping received")

        return handler

    msg_dispatcher().register_handler(HEADERS.UNPING, PingHandlerMock())

    async with message.get_msg_conn(peer) as connection:
        connection.send(ping)
    await asyncio.wait_for(check.wait(), 3)
    msg_dispatcher().remove_handler(HEADERS.UNPING)
    print("passed message")


if __name__ == "__main__":
    s1 = State("testing connection", test_connection)
    s2 = State("testing message", test_message)
    start_test([s1, s2])
