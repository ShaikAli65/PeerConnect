import pytest

from src.transfers.files import FileItem, calculate_chunk_size, validatename


def test_file_item_reads_existing_file_metadata_and_updates_path_on_rename(tmp_path):
    path = tmp_path / "note.txt"
    path.write_bytes(b"hello")

    item = FileItem(path, seeked=2)
    item.name = "renamed.txt"

    assert item.size == 5
    assert item.seeked == 2
    assert item.path == tmp_path / "renamed.txt"
    assert tuple(item) == ("renamed.txt", 5, 2)


def test_file_item_serializes_and_loads_metadata_under_download_path(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"payload")
    item = FileItem(source, seeked=3)

    loaded = FileItem.load_from(bytes(item), tmp_path / "downloads")

    assert loaded.name == "source.txt"
    assert loaded.size == 7
    assert loaded.seeked == 3
    assert loaded.path == tmp_path / "downloads" / "source.txt"


def test_validatename_assigns_next_available_name(tmp_path):
    (tmp_path / "report.txt").write_text("one")
    (tmp_path / "report (1).txt").write_text("two")
    item = FileItem(tmp_path / "report.txt", seeked=0)

    assert validatename(item, tmp_path) == "report (2).txt"
    assert item.name == "report (2).txt"
    assert item.path == tmp_path / "report (2).txt"


def test_file_item_error_extension_can_be_restored(tmp_path):
    path = tmp_path / "broken.txt"
    path.write_bytes(b"partial")
    item = FileItem(path, seeked=0)

    assert item.add_error_ext(".error") == "broken.error"
    assert not path.exists()
    assert item.path == tmp_path / "broken.error"

    assert item.remove_error_ext() == "broken.txt"
    assert item.path == path
    assert path.read_bytes() == b"partial"


def test_remove_error_extension_requires_original_extension(tmp_path):
    path = tmp_path / "plain.txt"
    path.write_bytes(b"data")
    item = FileItem(path, seeked=0)

    with pytest.raises(ValueError):
        item.remove_error_ext()


@pytest.mark.parametrize(
    ("file_size", "expected"),
    [
        (0, 64 * 1024),
        (1024, 64 * 1024),
        ((2**30) * 10, (2**20) * 2),
    ],
)
def test_calculate_chunk_size_boundaries(file_size, expected):
    assert calculate_chunk_size(file_size) == expected


def test_calculate_chunk_size_is_aligned_between_boundaries():
    chunk_size = calculate_chunk_size(25 * 1024 * 1024)

    assert 64 * 1024 < chunk_size < (2**20) * 2
    assert chunk_size % 1024 == 0
