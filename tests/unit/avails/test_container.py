import pytest

from src.avails.container import PeerDict, TransferBookBucket, TransfersBook
from src.avails import container


class DummyHandle:
    def __init__(self, transfer_id, peer_id):
        self.id = transfer_id
        self.peer_id = peer_id

    def __repr__(self):
        return f"DummyHandle(id={self.id!r}, peer_id={self.peer_id!r})"


class DummyPeer:
    def __init__(self, peer_id, username):
        self.peer_id = peer_id
        self.username = username
        self.update_count = 0

    def update(self, other):
        self.username = other.username
        self.update_count += 1

    def __repr__(self):
        return f"DummyPeer(peer_id={self.peer_id!r}, username={self.username!r})"


def handle_ids(handles):
    return {handle.id for handle in handles}


def test_transfers_book_public_api_returns_handles_not_records():
    book = TransfersBook()
    handle = DummyHandle("transfer-1", "peer-1")

    assert "TransferRecord" not in container.__all__
    assert book.add(handle, "files") is handle
    assert book.get("transfer-1") is handle
    assert book.require("transfer-1") is handle
    assert book.get_running("transfer-1") is handle
    assert book.get_many() == (handle,)
    assert tuple(book) == (handle,)

    moved = book.move("transfer-1", TransferBookBucket.COMPLETED)

    assert moved is handle
    assert book.get_running("transfer-1") is None
    assert book.get_completed("transfer-1") is handle
    assert book.update_completed("transfer-1", kind="renamed") is handle
    assert book.delete_completed("transfer-1") is handle
    assert book.get("transfer-1") is None
    assert len(book) == 0


def test_transfers_book_indexes_by_peer_and_bucket():
    book = TransfersBook()
    running_peer_1 = DummyHandle("running-peer-1", "peer-1")
    running_peer_2 = DummyHandle("running-peer-2", "peer-2")
    scheduled_many = DummyHandle("scheduled-many", "unused")

    book.add(running_peer_1, "files")
    book.add(running_peer_2, "directory")
    book.add(
        scheduled_many,
        "otm",
        bucket=TransferBookBucket.SCHEDULED,
        peer_ids=("peer-1", "peer-2"),
    )

    assert handle_ids(book.get_for_peer("peer-1")) == {"running-peer-1", "scheduled-many"}
    assert handle_ids(book.get_running_for_peer("peer-1")) == {"running-peer-1"}
    assert handle_ids(book.get_scheduled_for_peer("peer-2")) == {"scheduled-many"}

    moved = book.move_for_peer(
        "peer-2",
        TransferBookBucket.SCHEDULED,
        current_bucket=TransferBookBucket.RUNNING,
    )

    assert handle_ids(moved) == {"running-peer-2"}
    assert book.get_running("running-peer-2") is None
    assert book.get_scheduled("running-peer-2") is running_peer_2

    deleted = book.delete_scheduled_for_peer("peer-1")

    assert handle_ids(deleted) == {"scheduled-many"}
    assert book.get_scheduled("scheduled-many") is None
    assert book.get_scheduled("running-peer-2") is running_peer_2


def test_transfers_book_update_can_replace_handle_and_peer_indexes():
    book = TransfersBook()
    old_handle = DummyHandle("transfer-1", "peer-1")
    new_handle = DummyHandle("transfer-1", "peer-2")

    book.add(old_handle, "files")

    assert book.update("transfer-1", handle=new_handle, peer_id="peer-2") is new_handle
    assert book.get("transfer-1") is new_handle
    assert book.get_for_peer("peer-1") == ()
    assert book.get_for_peer("peer-2") == (new_handle,)


def test_transfers_book_duplicate_and_missing_require_errors():
    book = TransfersBook()
    handle = DummyHandle("transfer-1", "peer-1")

    book.add(handle, "files")

    with pytest.raises(KeyError):
        book.add(handle, "files")

    with pytest.raises(KeyError):
        book.require("missing-transfer")


def test_peer_dict_add_update_extend_remove_iter_and_clear():
    peers = PeerDict()
    original = DummyPeer("peer-1", "old-name")
    replacement = DummyPeer("peer-1", "new-name")
    second = DummyPeer("peer-2", "second")

    peers.add_peer(original)
    peers.add_peer(replacement)
    peers.extend([second])

    assert peers.get_peer("peer-1") is original
    assert peers.get_peer("peer-1").username == "new-name"
    assert original.update_count == 1
    assert peers.get_peer("peer-2") is second
    assert set(peers) == {original, second}
    assert set(peers.peers()) == {original, second}
    assert peers.remove_peer("peer-2") is second
    assert peers.remove_peer("missing") is None

    peers.clear()

    assert len(peers) == 0
