import pytest

from src.transfers.files import FileItem, FileItemReader, FileItemWriter


async def collect_reader(reader):
    chunks = []
    async with reader.start_reading() as reading:
        async for chunk in reading:
            chunks.append(bytes(chunk))
    return b"".join(chunks)


@pytest.mark.asyncio
async def test_file_item_reader_reads_only_configured_bounds(tmp_path, run_executor_inline):
    path = tmp_path / "data.bin"
    path.write_bytes(b"abcdefghi")
    item = FileItem(path, seeked=2)
    reader = FileItemReader(item, chunk_size=3)
    reader.set_bounds(2, 8)

    data = await collect_reader(reader)

    assert data == b"cdefgh"
    assert reader.seek_start_pos == 2
    assert reader.seek_end_pos == 8
    assert reader.seek_pos == 8


@pytest.mark.asyncio
async def test_file_item_writer_creates_new_file_and_tracks_seek(tmp_path, run_executor_inline):
    path = tmp_path / "created.bin"
    item = FileItem(path, seeked=0)
    item.size = 5
    writer = FileItemWriter(item)

    async with writer.start_writing():
        assert await writer.write(b"hello") == 5

    assert path.read_bytes() == b"hello"
    assert writer.seek_pos == 5


@pytest.mark.asyncio
async def test_file_item_writer_resumes_existing_file_at_seeked_offset(tmp_path, run_executor_inline):
    path = tmp_path / "resume.bin"
    path.write_bytes(b"hello_____")
    item = FileItem(path, seeked=5)
    item.size = 10
    writer = FileItemWriter(item)

    async with writer.start_writing():
        assert await writer.write(b"world") == 5

    assert path.read_bytes() == b"helloworld"
    assert writer.seek_pos == 10


@pytest.mark.asyncio
async def test_file_item_writer_refuses_to_resume_missing_file(tmp_path, run_executor_inline):
    item = FileItem(tmp_path / "missing.bin", seeked=4)
    item.size = 8
    writer = FileItemWriter(item)

    with pytest.raises(FileNotFoundError):
        async with writer.start_writing():
            pass


@pytest.mark.asyncio
async def test_file_item_writer_does_not_overwrite_existing_file_at_start(tmp_path, run_executor_inline):
    path = tmp_path / "exists.bin"
    path.write_bytes(b"keep")
    item = FileItem(path, seeked=0)
    writer = FileItemWriter(item)

    with pytest.raises(FileExistsError):
        async with writer.start_writing():
            pass

    assert path.read_bytes() == b"keep"
