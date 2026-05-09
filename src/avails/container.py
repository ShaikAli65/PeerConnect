"""
Contains simple storages
1. TransfersBookKeeper
2. TransfersBook
3. PeerDict
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from itertools import count
from typing import Any, Iterable, ValuesView
from weakref import WeakSet

from src.avails.bases import HasPeerId
from src.avails.remotepeer import RemotePeer

__match_type_hint = r":\s*([A-Za-z_]\w*(?:\s*\|\s*[A-Za-z_]\w*)*)(?=[,)])"

__all__ = (
    "PeerDict",
    "TransferBookBucket",
    "TransfersBook",
    "TransfersBookKeeper",
)


class PeerDict(dict):
    __slots__ = ()

    def get_peer(self, peer_id) -> RemotePeer:
        return self[peer_id]

    def add_peer(self, peer_obj: RemotePeer | HasPeerId):
        """Adds peer to dictionary

        If peer_obj with peer_id is already there in dict, then calls `RemotePeer.update` that
        changes/updates underlying attribute values inplace, this ensures that object references are maintained as-is.

        If you want to force the addition, call remove_peer first.

        Args:
            peer_obj(RemotePeer): peer object to add into dict.
        """

        if peer := self.get(peer_obj.peer_id, None):
            peer.update(peer_obj)
        else:
            self[peer_obj.peer_id] = peer_obj

    def extend(self, iterable_of_peer_objects: Iterable[RemotePeer | HasPeerId]):
        for peer_obj in iterable_of_peer_objects:
            self[peer_obj.peer_id] = peer_obj

    def remove_peer(self, peer_id: str):
        return self.pop(peer_id, None)

    def peers(self) -> ValuesView[RemotePeer]:
        return self.values()

    def clear(self):
        super().clear()

    def __str__(self):
        return ", ".join(x.__repr__() for x in self.values())

    def __iter__(self):
        return self.values().__iter__()

    def __repr__(self):
        return f"PeerDict({self})"


class TransferBookBucket(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    SCHEDULED = "scheduled"


@dataclass(frozen=True, slots=True)
class _TransferRecord:
    transfer_id: str
    handle: Any
    bucket: TransferBookBucket
    peer_ids: frozenset[str] = field(default_factory=frozenset)
    kind: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)


_MISSING = object()


class TransfersBook:
    """Table-like in-memory storage for transfer records.

    A transfer is stored once in ``_rows`` and exposed through secondary indexes
    for bucket and peer lookups. Completed records are kept strongly until
    explicitly deleted or pruned, which keeps lookups deterministic.
    """

    _id_counter = count()
    __slots__ = "_rows", "_by_bucket", "_by_peer", "_by_peer_bucket"

    def __init__(self):
        self._rows: dict[str, _TransferRecord] = {}
        self._by_bucket: dict[TransferBookBucket, set[str]] = defaultdict(set)
        self._by_peer: dict[str, set[str]] = defaultdict(set)
        self._by_peer_bucket: dict[tuple[str, TransferBookBucket], set[str]] = defaultdict(set)

    @classmethod
    def get_new_id(cls):
        return str(next(cls._id_counter))

    def add(
          self,
          handle,
          kind,
          *,
          transfer_id: str | None = None,
          bucket: TransferBookBucket | str = TransferBookBucket.RUNNING,
          peer_id: str | None = None,
          peer_ids: Iterable[str] | None = None,
    ):
        transfer_id = transfer_id or self._transfer_id_from(handle)
        if transfer_id in self._rows:
            raise KeyError(f"transfer {transfer_id!r} already exists")

        record = _TransferRecord(
            transfer_id=transfer_id,
            handle=handle,
            bucket=self._normalize_bucket(bucket),
            peer_ids=self._normalize_peer_ids(handle, peer_id=peer_id, peer_ids=peer_ids),
            kind=kind,
        )
        self._rows[transfer_id] = record
        self._index(record)
        return handle

    def get(self, transfer_id: str, bucket: TransferBookBucket | str | None = None):
        return getattr(self._get(transfer_id, bucket), 'handle', None)

    def _get(
          self,
          transfer_id: str,
          bucket: TransferBookBucket | str | None = None,
    ) -> _TransferRecord | None:
        record = self._rows.get(transfer_id)
        if record is None:
            return None
        if bucket is not None and record.bucket is not self._normalize_bucket(bucket):
            return None
        return record

    def require(self, transfer_id: str, bucket: TransferBookBucket | str | None = None):
        return self._require_record(transfer_id, bucket).handle

    def _require_record(
          self,
          transfer_id: str,
          bucket: TransferBookBucket | str | None = None,
    ) -> _TransferRecord:
        record = self._get(transfer_id, bucket)
        if record is None:
            raise KeyError(f"transfer {transfer_id!r} not found")
        return record

    def update(self, transfer_id: str, **changes):
        return self._update(transfer_id, **changes).handle

    def _update(
          self,
          transfer_id: str,
          *,
          bucket: TransferBookBucket | str | object = _MISSING,
          handle: Any = _MISSING,
          peer_id: str | None | object = _MISSING,
          peer_ids: Iterable[str] | object = _MISSING,
          kind: str | None | object = _MISSING,
    ) -> _TransferRecord:
        old = self._require_record(transfer_id)
        self._unindex(old)

        changes = {}
        if bucket is not _MISSING:
            changes["bucket"] = self._normalize_bucket(bucket)
        if handle is not _MISSING:
            changes["handle"] = handle
        if peer_id is not _MISSING or peer_ids is not _MISSING:
            changes["peer_ids"] = self._normalize_peer_ids(
                changes.get("handle", old.handle),
                peer_id=None if peer_id is _MISSING else peer_id,
                peer_ids=None if peer_ids is _MISSING else peer_ids,
            )
        if kind is not _MISSING:
            changes["kind"] = kind

        changes["updated_at"] = time.monotonic()

        new = replace(old, **changes)
        self._rows[transfer_id] = new
        self._index(new)
        return new

    def move(self, transfer_id: str, bucket: TransferBookBucket | str):
        return self._update(transfer_id, bucket=bucket).handle

    def delete(self, transfer_id: str, bucket: TransferBookBucket | str | None = None):
        deleted = self._delete(transfer_id, bucket)
        return getattr(deleted, 'handle', None)

    def _delete(
          self,
          transfer_id: str,
          bucket: TransferBookBucket | str | None = None,
    ) -> _TransferRecord | None:
        record = self._get(transfer_id, bucket)
        if record is None:
            return None
        self._unindex(record)
        del self._rows[transfer_id]
        return record

    def _get_many(
          self,
          bucket: TransferBookBucket | str | None = None,
    ) -> tuple[_TransferRecord, ...]:
        if bucket is None:
            transfer_ids = self._rows.keys()
        else:
            transfer_ids = self._by_bucket.get(self._normalize_bucket(bucket), ())
        return tuple(self._rows[transfer_id] for transfer_id in transfer_ids)

    def get_many(self, bucket: TransferBookBucket | str | None = None):
        return tuple(record.handle for record in self._get_many(bucket))

    def _get_for_peer(
          self,
          peer_id: str,
          bucket: TransferBookBucket | str | None = None,
    ) -> tuple[_TransferRecord, ...]:
        if bucket is None:
            transfer_ids = self._by_peer.get(peer_id, ())
        else:
            transfer_ids = self._by_peer_bucket.get(
                (peer_id, self._normalize_bucket(bucket)),
                (),
            )
        return tuple(self._rows[transfer_id] for transfer_id in transfer_ids)

    def get_for_peer(self, peer_id: str, bucket: TransferBookBucket | str | None = None):
        return tuple(record.handle for record in self._get_for_peer(peer_id, bucket))

    def _update_for_peer(
          self,
          peer_id: str,
          *,
          current_bucket: TransferBookBucket | str | None = None,
          **changes,
    ):
        records = self._get_for_peer(peer_id, current_bucket)
        return tuple(self._update(record.transfer_id, **changes).handle for record in records)

    def move_for_peer(
          self,
          peer_id: str,
          bucket: TransferBookBucket | str,
          *,
          current_bucket: TransferBookBucket | str | None = None,
    ):
        return self._update_for_peer(peer_id, current_bucket=current_bucket, bucket=bucket)

    def _delete_for_peer(
          self,
          peer_id: str,
          bucket: TransferBookBucket | str | None = None,
    ):
        records = self._get_for_peer(peer_id, bucket)
        return tuple(
            deleted.handle for record in records
            if (deleted := self._delete(record.transfer_id)) is not None
        )

    def get_running(self, transfer_id: str):
        return self.get(transfer_id, TransferBookBucket.RUNNING)

    def update_running(self, transfer_id: str, **changes):
        self._require_record(transfer_id, TransferBookBucket.RUNNING)
        return self._update(transfer_id, **changes).handle

    def delete_running(self, transfer_id: str):
        return self.delete(transfer_id, TransferBookBucket.RUNNING)

    def get_completed(self, transfer_id: str):
        return self.get(transfer_id, TransferBookBucket.COMPLETED)

    def update_completed(self, transfer_id: str, **changes):
        self._require_record(transfer_id, TransferBookBucket.COMPLETED)
        return self._update(transfer_id, **changes).handle

    def delete_completed(self, transfer_id: str):
        return self.delete(transfer_id, TransferBookBucket.COMPLETED)

    def get_scheduled(self, transfer_id: str):
        return self.get(transfer_id, TransferBookBucket.SCHEDULED)

    def update_scheduled(self, transfer_id: str, **changes):
        self._require_record(transfer_id, TransferBookBucket.SCHEDULED)
        return self._update(transfer_id, **changes).handle

    def delete_scheduled(self, transfer_id: str):
        return self.delete(transfer_id, TransferBookBucket.SCHEDULED)

    def get_running_for_peer(self, peer_id: str):
        return self.get_for_peer(peer_id, TransferBookBucket.RUNNING)

    def update_running_for_peer(self, peer_id: str, **changes):
        return self._update_for_peer(
            peer_id,
            current_bucket=TransferBookBucket.RUNNING,
            **changes,
        )

    def delete_running_for_peer(self, peer_id: str):
        return self._delete_for_peer(peer_id, TransferBookBucket.RUNNING)

    def get_completed_for_peer(self, peer_id: str):
        return self.get_for_peer(peer_id, TransferBookBucket.COMPLETED)

    def update_completed_for_peer(self, peer_id: str, **changes):
        return self._update_for_peer(
            peer_id,
            current_bucket=TransferBookBucket.COMPLETED,
            **changes,
        )

    def delete_completed_for_peer(self, peer_id: str):
        return self._delete_for_peer(peer_id, TransferBookBucket.COMPLETED)

    def get_scheduled_for_peer(self, peer_id: str):
        return self.get_for_peer(peer_id, TransferBookBucket.SCHEDULED)

    def update_scheduled_for_peer(self, peer_id: str, **changes):
        return self._update_for_peer(
            peer_id,
            current_bucket=TransferBookBucket.SCHEDULED,
            **changes,
        )

    def delete_scheduled_for_peer(self, peer_id: str):
        return self._delete_for_peer(peer_id, TransferBookBucket.SCHEDULED)

    def prune_completed(self, older_than: float):
        now = time.monotonic()
        records = self._get_many(TransferBookBucket.COMPLETED)
        return tuple(
            deleted.handle for record in records
            if now - record.updated_at >= older_than
            if (deleted := self._delete(record.transfer_id)) is not None
        )

    def clear(self):
        self._rows.clear()
        self._by_bucket.clear()
        self._by_peer.clear()
        self._by_peer_bucket.clear()

    def __contains__(self, transfer_id: str):
        return transfer_id in self._rows

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return (record.handle for record in self._rows.values())

    def __repr__(self):
        buckets = {
            bucket.value: len(self._by_bucket.get(bucket, ()))
            for bucket in TransferBookBucket
        }
        return f"{self.__class__.__name__}(total={len(self)}, buckets={buckets})"

    def _index(self, record: _TransferRecord):
        self._by_bucket[record.bucket].add(record.transfer_id)
        for peer_id in record.peer_ids:
            self._by_peer[peer_id].add(record.transfer_id)
            self._by_peer_bucket[(peer_id, record.bucket)].add(record.transfer_id)

    def _unindex(self, record: _TransferRecord):
        self._discard(self._by_bucket, record.bucket, record.transfer_id)
        for peer_id in record.peer_ids:
            self._discard(self._by_peer, peer_id, record.transfer_id)
            self._discard(self._by_peer_bucket, (peer_id, record.bucket), record.transfer_id)

    @staticmethod
    def _discard(index, key, transfer_id):
        values = index.get(key)
        if values is None:
            return
        values.discard(transfer_id)
        if not values:
            del index[key]

    @staticmethod
    def _normalize_bucket(bucket: TransferBookBucket | str) -> TransferBookBucket:
        if isinstance(bucket, TransferBookBucket):
            return bucket
        return TransferBookBucket(str(bucket).lower())

    @classmethod
    def _normalize_peer_ids(
          cls,
          handle,
          *,
          peer_id: str | None = None,
          peer_ids: Iterable[str] | None = None,
    ) -> frozenset[str]:
        if peer_ids is not None:
            return frozenset(str(item) for item in peer_ids)
        if peer_id is not None:
            return frozenset((str(peer_id),))
        if inferred_peer_id := cls._peer_id_from(handle):
            return frozenset((str(inferred_peer_id),))
        return frozenset()

    @staticmethod
    def _transfer_id_from(handle) -> str:
        try:
            return str(handle.id)
        except AttributeError as exp:
            raise ValueError("transfer_id is required when handle has no id") from exp

    @staticmethod
    def _peer_id_from(handle):
        if peer_id := getattr(handle, "peer_id", None):
            return peer_id
        peer = getattr(handle, "peer", None)
        if peer is not None:
            return getattr(peer, "peer_id", None)
        return None


class TransfersBookKeeper:
    """Stores file/dir handles/pools references

    All the containers are two-dimensional
    {
        peer id: set{file_handles/pools}  # uses set
    }
    completed : stores weak references to file handles/pools that are completed
    current : stores strong references to file handles/pools that are running
    continued : stores strong references file handles/pools that are paused or are meant to resumed
    """

    _id_counter = count()
    __slots__ = "__continued", "__completed", "__current", "__scheduled"
    __annotations__ = {
        "__continued": dict,
        "__completed": dict,
        "__current": dict,
        "__scheduled": dict,
    }

    def __init__(self):
        self.__continued = defaultdict(set)
        self.__scheduled = {}
        self.__completed = defaultdict(WeakSet)
        self.__current = defaultdict(set)

    def add_to_current(self, peer_id, transfer_handle):
        self.__current[peer_id].add(transfer_handle)
        self.__continued[peer_id].discard(transfer_handle)

    def add_to_completed(self, peer_id, transfer_handle):
        self.__current[peer_id].discard(transfer_handle)
        self.__continued[peer_id].discard(transfer_handle)
        self.__completed[peer_id].add(transfer_handle)

    def add_to_scheduled(self, transfer_handle):
        self.__scheduled[transfer_handle.id] = transfer_handle

    def add_to_continued(self, peer_id, file_pool):
        self.__current[peer_id].discard(file_pool)
        self.__continued[peer_id].add(file_pool)

    def continued_to_completed(self, peer_id, file_pool):
        self.__continued[peer_id].remove(file_pool)
        self.__completed[peer_id].add(file_pool)

    @staticmethod
    def __check_container(peer_id, file_id, container):
        if file_id:
            return next((h for h in container[peer_id] if h.id == file_id), None)
        return iter(container[peer_id])

    def get_running_transfers(self, peer_id, file_id=None):
        return self.__check_container(peer_id, file_id, self.__current)

    def get_completed_transfer(self, peer_id, file_id):
        return self.__check_container(peer_id, file_id, self.__completed)

    def get_continued_file(self, peer_id, file_id):
        return self.__check_container(peer_id, file_id, self.__continued)

    def get_scheduled(self, file_id):
        return self.__scheduled.get(file_id, None)

    def get_transfer(self, peer_id, file_id):
        try:
            return self.get_running_transfers(peer_id, file_id)
        except StopIteration:
            pass
        try:
            return self.get_continued_file(peer_id, file_id)
        except StopIteration:
            pass
        try:
            return self.get_completed_transfer(peer_id, file_id)
        except StopIteration:
            pass
        return None

    def remove_transfer(self, peer_id, transfer_handle):
        self.__current[peer_id].discard(transfer_handle)
        self.__continued[peer_id].discard(transfer_handle)
        self.__completed[peer_id].discard(transfer_handle)
        if transfer_handle.id in self.__scheduled:
            del self.__scheduled[transfer_handle]

    @property
    def continued(self):
        return self.__continued.values()

    @property
    def completed(self):
        return self.__completed.values()

    @property
    def current(self):
        return self.__current.values()

    @classmethod
    def get_new_id(cls):
        return str(next(cls._id_counter))

    def get_running_transfer(self, peer_id):
        if running := self.get_running_transfers(peer_id):
            return next(running, None)
        return None

    def __repr__(self):
        return f"{tuple(self.current)=}, {tuple(self.completed)=}, {tuple(self.continued)=}"
