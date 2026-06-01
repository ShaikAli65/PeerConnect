import asyncio
import random

import pytest

from src.avails.exceptions import FailedToSend
from src.net.msg_socket import MessageSocket


class RecordingTransport:
    def __init__(self, fail_first=False):
        self.sent = []
        self.fail_first = fail_first

    async def send(self, data):
        if self.fail_first:
            self.fail_first = False
            raise ConnectionError("disconnected")
        self.sent.append(data)
        return len(data)


class RandomlyFailingTransport:
    def __init__(self, seed, fail_rate):
        self._random = random.Random(seed)
        self.fail_rate = fail_rate
        self.attempted = []
        self.sent = []

    async def send(self, data):
        self.attempted.append(data)
        if self._random.random() < self.fail_rate:
            raise ConnectionError("random connection failure")
        self.sent.append(data)
        return len(data)


@pytest.mark.asyncio
async def test_context_exit_fails_buffered_call_instead_of_hanging():
    msg_socket = MessageSocket(buffer_size=1)
    await msg_socket.__aenter__()
    send_task = asyncio.create_task(msg_socket("pending"))
    await asyncio.sleep(0)

    await asyncio.wait_for(msg_socket.__aexit__(None, None, None), timeout=1)

    with pytest.raises(FailedToSend):
        await send_task


@pytest.mark.asyncio
async def test_ordered_failed_sends_raise_buffer_and_replay_when_transport_recovers():
    failing_transport = RandomlyFailingTransport(seed=1, fail_rate=0.95)
    recovery_transport = RecordingTransport()
    messages = [f"message-{index}".encode() for index in range(5)]
    buffered_futures = []

    async with MessageSocket(
          failing_transport,
          ordering=True,
          raise_on_send_failure=True,
    ).context_manager() as msg_socket:
        for message in messages:
            with pytest.raises(FailedToSend) as exc_info:
                await msg_socket(message)

            assert exc_info.value.item == message
            assert not exc_info.value.future.done()
            buffered_futures.append(exc_info.value.future)

        assert msg_socket.buffer.qsize() == len(messages)

        await msg_socket.update_transport(recovery_transport)

        results = await asyncio.wait_for(
            asyncio.gather(*buffered_futures),
            timeout=1,
        )

    assert failing_transport.attempted == [messages[0]]
    assert failing_transport.sent == []
    assert recovery_transport.sent == messages
    assert results == [len(message) for message in messages]
