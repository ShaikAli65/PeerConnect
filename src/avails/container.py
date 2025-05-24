"""
Contains simple storages used across the peer connect
1. TransfersBookKeeper
2. PeerDict
"""

from collections import defaultdict
from itertools import count
from typing import Iterable, TYPE_CHECKING, ValuesView
from weakref import WeakSet

from src.avails.bases import HasID, HasIdProperty, HasPeerId
from src.avails.remotepeer import RemotePeer

__match_type_hint = r":\s*([A-Za-z_]\w*(?:\s*\|\s*[A-Za-z_]\w*)*)(?=[,)])"

__all__ = (
    "PeerDict",
    "TransfersBookKeeper",
)


# (self, peer_id:  str, transfer_handle: HasID | HasIdProperty)


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
        self.clear()

    def __str__(self):
        return ", ".join(x.__repr__() for x in self.values())

    def __iter__(self):
        return self.values().__iter__()


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
        self.__continued = defaultdict(set)  # str: flip[PeerFilePool]
        self.__scheduled = {}
        self.__completed = defaultdict(WeakSet)  # str: flip[PeerFilePool]
        self.__current = defaultdict(set)  # str: flip[PeerFilePool]

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


if TYPE_CHECKING:
    from src.transfers.abc import AbstractTransferHandle

    class TransfersBookKeeper:
        def add_to_current(
              self,
              peer_id: str,
              transfer_handle: AbstractTransferHandle | HasID | HasIdProperty,
        ): ...

        def add_to_completed(
              self,
              peer_id: str,
              transfer_handle: AbstractTransferHandle | HasID | HasIdProperty,
        ): ...

        def add_to_scheduled(
              self, key, transfer_handle: AbstractTransferHandle | HasID | HasIdProperty
        ): ...

        def add_to_continued(self, peer_id: str, file_pool): ...

        def swap(self, peer_id: str, file_pool): ...

        def get_running_transfers(
              self, peer_id: str, file_id=None
        ) -> AbstractTransferHandle: ...

        def get_completed_transfer(
              self, peer_id: str, file_id
        ) -> AbstractTransferHandle: ...

        def get_continued_file(
              self, peer_id: str, file_id
        ) -> AbstractTransferHandle: ...

        def get_scheduled(self, file_id) -> AbstractTransferHandle: ...

        def get_transfer(self, peer_id: str, file_id) -> AbstractTransferHandle: ...

        def get_running_transfer(self, peer_id) -> AbstractTransferHandle | None: ...

        @property
        def continued(self) -> int: ...  # noqa

        @property
        def completed(self) -> int: ...  # noqa

        @property
        def current(self) -> int: ...  # noqa

        @classmethod
        def get_new_id(cls) -> str: ...

        def check_running(self, peer_id) -> AbstractTransferHandle | None: ...
