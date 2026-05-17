import struct

import pytest
import umsgpack

from src.avails.exceptions import TransferIncomplete
from src.transfers.files.directory import DirReceiver, rename_directory_with_increment

from tests.utils.transfers import AsyncByteStream, DummyStatus


def test_rename_directory_with_increment_creates_next_available_directory(tmp_path):
    (tmp_path / "photos").mkdir()
    (tmp_path / "photos(1)").mkdir()

    created = rename_directory_with_increment(tmp_path, "photos")

    assert created == tmp_path / "photos(2)"
    assert created.is_dir()


@pytest.mark.asyncio
async def test_dir_receiver_decodes_parent_and_item_name_parts(tmp_path):
    payload = umsgpack.dumps(("nested/path", "file.txt"))
    stream = AsyncByteStream(struct.pack("!I", len(payload)) + payload)
    receiver = DirReceiver(None, "transfer-1", tmp_path, DummyStatus())
    receiver.connection_made(stream)
    assert await receiver._recv_parts() == ("nested/path", "file.txt")


@pytest.mark.asyncio
async def test_dir_receiver_rejects_malformed_parts(tmp_path):
    stream = AsyncByteStream(struct.pack("!I", 2) + b"\xc1\xc1")
    receiver = DirReceiver(None, "transfer-1", tmp_path, DummyStatus())
    receiver.connection_made(stream)

    with pytest.raises(TransferIncomplete):
        await receiver._recv_parts()
