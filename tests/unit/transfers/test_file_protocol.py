import struct

import pytest

from src.transfers import HEADERS
from src.transfers.files import FileItem
from src.transfers.files.receiver import Receiver
from src.transfers.files.sender import Sender

from tests.utils.transfers import AsyncByteStream, DummyStatus


@pytest.mark.asyncio
async def test_sender_encodes_file_metadata_as_length_prefixed_file_item(tmp_path):
    path = tmp_path / "send.txt"
    path.write_bytes(b"payload")
    item = FileItem(path, seeked=2)
    stream = AsyncByteStream()
    sender = Sender(None, "transfer-1", [item], DummyStatus())
    sender.connection_made(stream)

    await sender.send_file_metadata(item)

    assert len(stream.sent) == 1
    payload = stream.sent[0]
    metadata_size = struct.unpack("!I", payload[:4])[0]
    loaded = FileItem.load_from(payload[4:4 + metadata_size], tmp_path / "downloads")
    assert metadata_size == len(payload) - 4
    assert loaded.name == "send.txt"
    assert loaded.size == 7
    assert loaded.seeked == 2


@pytest.mark.asyncio
async def test_receiver_decodes_length_prefixed_file_metadata(tmp_path):
    source = tmp_path / "incoming.txt"
    source.write_bytes(b"content")
    item = FileItem(source, seeked=4)
    metadata = bytes(item)
    stream = AsyncByteStream(struct.pack("!I", len(metadata)) + metadata)
    receiver = Receiver(None, "transfer-1", tmp_path / "downloads", DummyStatus())
    receiver.connection_made(stream)

    decoded = await receiver._recv_file_item()

    assert decoded.path == tmp_path / "downloads" / "incoming.txt"
    assert decoded.size == 7
    assert decoded.seeked == 4


@pytest.mark.asyncio
async def test_receiver_writes_single_file_from_chunked_stream(tmp_path, run_executor_inline):
    item = FileItem(tmp_path / "received.bin", seeked=0)
    item.size = 11
    stream = AsyncByteStream(b"hello world")
    receiver = Receiver(None, "transfer-1", tmp_path, DummyStatus())
    receiver.connection_made(stream)

    from src.transfers.files import FileItemWriter

    writer = FileItemWriter(item)
    writes = []
    async for written in receiver._receive_single_file(writer):
        writes.append(written)

    assert writes == [11]
    assert item.path.read_bytes() == b"hello world"
    assert writer.seek_pos == 11


@pytest.mark.asyncio
async def test_receiver_acknowledges_end_of_transfer_without_file_payload(tmp_path):
    stream = AsyncByteStream(HEADERS.END_OF_TRANSFER)
    receiver = Receiver(None, "transfer-1", tmp_path, DummyStatus())
    receiver.connection_made(stream)

    yielded = [item async for item in receiver.start_transfer()]

    assert yielded == []
    assert stream.sent == [HEADERS.END_OF_TRANSFER]
