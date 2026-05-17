import pytest

from src.transfers.files import FileItem
from src.transfers.files._merge import merge_all_and_delete


@pytest.mark.asyncio
async def test_merge_all_and_delete_appends_parts_in_index_order(tmp_path, run_executor_inline):
    part_two = tmp_path / "part-2.bin"
    part_one = tmp_path / "part-1.bin"
    part_three = tmp_path / "part-3.bin"
    final_path = tmp_path / "final.bin"
    part_two.write_bytes(b"world")
    part_one.write_bytes(b"hello ")
    part_three.write_bytes(b"!")

    parts = {
        2: FileItem(part_two, seeked=0),
        1: FileItem(part_one, seeked=0),
        3: FileItem(part_three, seeked=0),
    }
    final = FileItem(final_path, seeked=0)

    await merge_all_and_delete(final, parts)

    assert final_path.read_bytes() == b"hello world!"
    assert final.size == len(b"hello world!")
    assert not part_one.exists()
    assert not part_two.exists()
    assert not part_three.exists()
