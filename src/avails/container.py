import asyncio
import contextlib
import socket
from collections import OrderedDict, defaultdict
from itertools import count
from typing import Iterable, TYPE_CHECKING, Union, ValuesView
from weakref import WeakSet

import src.avails.connect as connect
from src.avails.bases import HasID, HasIdProperty, HasPeerId

"""
This module contains simple storages used across the peer connect
1. 
2. PeerDict
3. SafeSet
4. FileDict
5. SocketStore
6. SocketCache
"""


class PeerDict(dict):
    __slots__ = '__lock',

    def __init__(self):
        super().__init__()
        # self.__lock = threading.Lock()
        self.__lock = asyncio.Lock()

    if TYPE_CHECKING:
        from src.avails import RemotePeer
        RemotePeer = RemotePeer
    else:
        RemotePeer = None

    def get_peer(self, peer_id) -> RemotePeer:
        return self.get(peer_id, None)

    def add_peer(self, peer_obj: RemotePeer | HasPeerId):
        # with self.__lock:
        self[peer_obj.peer_id] = peer_obj

    def extend(self, iterable_of_peer_objects: Iterable[RemotePeer | HasPeerId]):
        for peer_obj in iterable_of_peer_objects:
            self[peer_obj.peer_id] = peer_obj

    def remove_peer(self, peer_id: str):
        return self.pop(peer_id, None)

    def peers(self) -> ValuesView[RemotePeer]:
        return self.values()

    def clear(self):
        with self.__lock:
            self.clear()

    def __str__(self):
        return ', '.join(x.__repr__() for x in self.values())

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
    __slots__ = '__continued', '__completed', '__current', '__scheduled'
    __annotations__ = {
        '__continued': dict,
        '__completed': dict,
        '__current': dict,
        '__scheduled': dict,
    }

    def __init__(self):
        self.__continued = defaultdict(set)  # str: flip[PeerFilePool]
        self.__scheduled = {}
        self.__completed = defaultdict(WeakSet)  # str: flip[PeerFilePool]
        self.__current = defaultdict(set)  # str: flip[PeerFilePool]

    def add_to_current(self, peer_id: str, transfer_handle: HasID | HasIdProperty):
        self.__current[peer_id].add(transfer_handle)
        self.__continued[peer_id].discard(transfer_handle)

    def add_to_completed(self, peer_id: str, transfer_handle: HasID | HasIdProperty):
        self.__current[peer_id].discard(transfer_handle)
        self.__continued[peer_id].discard(transfer_handle)
        self.__completed[peer_id].add(transfer_handle)

    def add_to_scheduled(self, key, transfer_handle: HasID | HasIdProperty):
        self.__scheduled[key] = transfer_handle

    def add_to_continued(self, peer_id: str, file_pool):
        self.__current[peer_id].discard(file_pool)
        self.__continued[peer_id].add(file_pool)

    def swap(self, peer_id: str, file_pool):
        self.__continued[peer_id].remove(file_pool)
        self.__completed[peer_id].add(file_pool)

    def _get_running_transfers(self, peer_id: str, file_id=None):
        if file_id:
            return next(file for file in self.__current[peer_id] if file.id == file_id)
        return list(self.__current[peer_id])

    def _get_completed_transfer(self, peer_id: str, file_id):
        return next(file for file in self.__completed[peer_id] if file.id == file_id)

    def _get_continued_file(self, peer_id: str, file_id):
        return next(file for file in self.__continued[peer_id] if file.id == file_id)

    def get_scheduled(self, file_id):
        return self.__scheduled.get(file_id, None)

    def get_transfer(self, peer_id: str, file_id):
        try:
            return self._get_running_transfers(peer_id, file_id)
        except StopIteration:
            pass
        try:
            return self._get_completed_transfer(peer_id, file_id)
        except StopIteration:
            pass
        try:
            return self._get_continued_file(peer_id, file_id)
        except StopIteration:
            pass
        return None

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

    def check_running(self, peer_id):
        if running := self._get_running_transfers(peer_id):
            return running[0]
        return None

    def stop_all_files(self):
        for file_set in self.__current.values():
            for file in file_set:
                file.break_loop()
        self.__continued.update(self.__current)
        self.__current.clear()
        return


class SocketStore:
    """
    a bare soft wrapper to close multiple sockets
    """
    __slots__ = 'storage',

    def __init__(self):
        self.storage = set()

    def add_socket(self, sock):
        self.storage.add(sock)

    def remove_socket(self, sock):
        self.storage.discard(sock)

    def close_all(self):
        for sock in self.storage:
            with contextlib.suppress(OSError, socket.error):
                sock.close()


class SocketCache:
    """
    Maintains a pool of active sockets between peers

    """

    def __init__(self, max_limit=4):
        self.socket_cache: dict[str: connect.Socket] = OrderedDict()
        self.max_limit = max_limit

    def add_peer_sock(self, peer_id: str, peer_socket):
        if len(self.socket_cache) >= self.max_limit:
            self.socket_cache.popitem(last=False)
        self.socket_cache[peer_id] = peer_socket
        return peer_socket

    def get_socket(self, peer_id) -> Union[connect.Socket, None]:
        sock = self.socket_cache.pop(peer_id, None)
        if sock:
            self.socket_cache[peer_id] = sock
        return sock

    def is_connected(self, peer_id) -> Union[connect.Socket, bool]:
        try:
            sock = self.socket_cache[peer_id]
            if connect.is_socket_connected(sock):
                return sock
            return False
        except KeyError:
            return False

    def remove_and_close(self, peer_id):
        try:
            sock = self.socket_cache[peer_id]
            del self.socket_cache[peer_id]
            sock.close()
        except KeyError:
            return
        except (OSError, socket.error):
            del self.socket_cache[peer_id]

    def clear(self):
        self.__close_all_socks()
        self.socket_cache.clear()

    def __close_all_socks(self):
        for sock in list(self.socket_cache.values()):
            try:
                sock.close()
            except Exception:  # noqa
                pass

    def __contains__(self, item: str):
        return item in self.socket_cache

    def __del__(self):
        self.__close_all_socks()
