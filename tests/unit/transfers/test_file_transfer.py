import asyncio

import pytest

from src.transfers import TransferState
from src.transfers.files import FileItem
from src.transfers.files import bigfile
from src.transfers.files.bigfile import Receiver as BigFileReceiver
from src.transfers.files.bigfile import Sender as BigFileSender
from src.transfers.files.directory import DirReceiver, DirSender
from src.transfers.files.receiver import Receiver
from src.transfers.files.sender import Sender

from tests.utils.transfers import DummyStatus


class MemoryEndpoint:
    def __init__(self, incoming, outgoing):
        self._incoming = incoming
        self._outgoing = outgoing
        self._buffer = bytearray()
        self.paused = False

    async def send(self, data):
        await self._outgoing.put(bytes(data))
        return len(data)

    async def recv(self, size):
        while len(self._buffer) < size:
            self._buffer.extend(await self._incoming.get())
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


def memory_connection_pair():
    left_to_right = asyncio.Queue()
    right_to_left = asyncio.Queue()
    return (
        MemoryEndpoint(right_to_left, left_to_right),
        MemoryEndpoint(left_to_right, right_to_left),
    )


class QueueStatus(DummyStatus):
    _sentinel = object()

    def __init__(self):
        super().__init__()
        self._queue = asyncio.Queue()
        self._closed = False
        self.frozen = False
        self.current_status = 0

    def freeze(self):
        self.frozen = True

    def unfreeze(self):
        self.frozen = False

    async def write_update(self, update):
        self.current_status += update
        self.updates.append(self.current_status)
        await self._queue.put(self.current_status)

    async def update_status(self, status):
        self.current_status = status
        self.updates.append(status)
        await self._queue.put(status)

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue.get()
        if item is self._sentinel:
            raise StopAsyncIteration
        return item

    async def close(self):
        self.closed += 1
        if not self._closed:
            self._closed = True
            await self._queue.put(self._sentinel)


async def consume(async_iterable):
    return [item async for item in async_iterable]


@pytest.mark.asyncio
async def test_file_sender_and_receiver_transfer_multiple_files(tmp_path, run_executor_inline):
    source_dir = tmp_path / "source"
    download_dir = tmp_path / "download"
    source_dir.mkdir()
    download_dir.mkdir()
    first = source_dir / "first.txt"
    second = source_dir / "second.bin"
    first.write_bytes(b"alpha")
    second.write_bytes(b"beta-gamma")
    file_items = [FileItem(first, 0), FileItem(second, 0)]
    sender_status = DummyStatus()
    receiver_status = DummyStatus()
    sender = Sender(None, "transfer-1", file_items, sender_status)
    receiver = Receiver(None, "transfer-1", download_dir, receiver_status)
    sender_conn, receiver_conn = memory_connection_pair()
    sender.connection_made(sender_conn)
    receiver.connection_made(receiver_conn)

    sender_updates, receiver_updates = await asyncio.gather(
        consume(sender.start_transfer()),
        consume(receiver.start_transfer()),
    )

    assert sender_updates == [5, 10]
    assert receiver_updates == [5, 10]
    assert (download_dir / "first.txt").read_bytes() == b"alpha"
    assert (download_dir / "second.bin").read_bytes() == b"beta-gamma"
    assert [item.seeked for item in file_items] == [5, 10]
    assert sender.state is TransferState.COMPLETED
    assert receiver.state is TransferState.COMPLETED
    assert sender.done.is_set()


@pytest.mark.asyncio
async def test_directory_sender_and_receiver_transfer_nested_tree(tmp_path, run_executor_inline):
    source_dir = tmp_path / "tree"
    download_dir = tmp_path / "received"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)
    download_dir.mkdir()
    (source_dir / "root.txt").write_bytes(b"root-data")
    (nested_dir / "child.txt").write_bytes(b"child-data")
    sender = DirSender(None, "dir-transfer", source_dir, DummyStatus())
    receiver = DirReceiver(None, "dir-transfer", download_dir, DummyStatus())
    sender_conn, receiver_conn = memory_connection_pair()
    sender.connection_made(sender_conn)
    receiver.connection_made(receiver_conn)

    sender_updates, receiver_updates = await asyncio.gather(
        consume(sender.start_transfer()),
        consume(receiver.start_transfer()),
    )

    assert sender_updates == [9, 10]
    assert receiver_updates == [(download_dir / "nested", None), 9, 10]
    assert (download_dir / "root.txt").read_bytes() == b"root-data"
    assert (download_dir / "nested" / "child.txt").read_bytes() == b"child-data"
    assert sender.state is TransferState.COMPLETED
    assert receiver.state is TransferState.COMPLETED


@pytest.mark.asyncio
async def test_bigfile_sender_and_receiver_transfer_parts_over_multiple_connections(
    tmp_path,
    monkeypatch,
    run_executor_inline,
):
    monkeypatch.setattr(bigfile, "CHUNK_SIZE", 5)
    source_path = tmp_path / "large.bin"
    final_path = tmp_path / "download" / "large.bin"
    final_path.parent.mkdir()
    payload = b"abcdefghijklmnop"
    source_path.write_bytes(payload)
    source_item = FileItem(source_path, 0)
    final_item = FileItem(final_path, 0)
    final_item.size = source_item.size
    sender_status = QueueStatus()
    receiver_status = QueueStatus()
    sender = BigFileSender(source_item, None, "big-transfer", sender_status)
    receiver = BigFileReceiver(None, "big-transfer", final_path.parent, receiver_status)
    receiver.current_transfer = final_item

    async with sender, receiver:
        for _ in range(2):
            sender_conn, receiver_conn = memory_connection_pair()
            sender.connection_made(sender_conn)
            receiver.connection_made(receiver_conn)

        sender_updates, receiver_updates = await asyncio.gather(
            consume(sender.start_transfer()),
            consume(receiver.start_transfer()),
        )

    assert final_path.read_bytes() == payload
    assert sender_updates[-1] == len(payload)
    assert receiver_updates[-1] == len(payload)
    assert len(receiver.parts) == 4
    assert sender.max_parts_count == 4
    assert receiver.state is TransferState.COMPLETED
    assert sender.done.is_set()
    assert receiver.done.is_set()
