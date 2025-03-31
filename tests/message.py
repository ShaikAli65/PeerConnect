import asyncio
import random

import _path  # noqa
from src.avails import WireData
from src.avails.events import MessageEvent
from src.core.app import AppType
from src.managers import message
from src.managers.statemanager import State
from src.transfers import HEADERS
from tests.test import get_a_peer, start_test


async def test_message(app_ctx: AppType):
    peer = get_a_peer()
    assert peer is not None

    check = asyncio.Event()

    ping = WireData(
        header=HEADERS.PING,
        peer_id=app_ctx.this_peer_id,
        msg_id=(ping_id := str(random.randint(1, 1000)))
    )

    def UNPingHandlerMock():
        async def handler(msg_event: MessageEvent):
            if msg_event.msg.msg_id == ping_id:
                check.set()
                print("ping received")

        return handler

    app_ctx.messages.dispatcher.register_handler(HEADERS.UNPING, UNPingHandlerMock())

    async with message.get_msg_conn(peer) as connection:
        await connection.send(ping)

    try:
        await asyncio.wait_for(check.wait(), 3)
    except TimeoutError:
        print("[TEST][FAILED] to send message reason: un ping not received")
    else:
        app_ctx.messages.dispatcher.remove_handler(HEADERS.UNPING)
        print("[TEST][PASSED]  message")


if __name__ == '__main__':
    s = State("testing message", test_message)
    start_test(s)
