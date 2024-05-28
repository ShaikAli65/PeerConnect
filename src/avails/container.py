import threading

from collections import deque, defaultdict
# from typing import ValuesView
# from .remotepeer import RemotePeer


class PeerDict:
    __slots__ = '__lock', '__dict'
    __annotations__ = {
        '__lock': threading.Lock,
        '__dict': dict
    }

    def __init__(self):
        self.__lock = threading.Lock()
        self.__dict = {}

    def get_peer(self, key):  # -> RemotePeer:
        with self.__lock:
            return self.__dict[key]

    def add_peer(self, key, value):  # RemotePeer):
        with self.__lock:
            self.__dict[key] = value

    def remove_peer(self, key):
        with self.__lock:
            self.__dict.pop(key, None)

    def peers(self):  # -> ValuesView[RemotePeer]:
        with self.__lock:
            return self.__dict.values()

    def clear(self):
        with self.__lock:
            self.__dict.clear()

    def __getitem__(self, key):  # -> RemotePeer:
        return self.__dict[key]

    def __setitem__(self, key, value):
        self.__dict[key] = value

    def __delitem__(self, key):
        del self.__dict[key]

    def __contains__(self, key):
        return key in self.__dict

    def __iter__(self):
        return self.__dict.__iter__()

    def __len__(self):
        return self.__dict.__len__()

    def __str__(self):
        return ', '.join(x.__repr__() for x in self.__dict.values())

    def __repr__(self):
        return self.__dict.__repr__()


class CustomSet:
    """
    CustomSet is a thread safe set implementation with additional features.

    """
    __annotations__ = {
        '__list': set,
        '__lock': threading.Lock
    }

    __slots__ = '__list', '__lock', 'changes'

    def __init__(self):
        self.__list = set()
        self.__lock = threading.Lock()
        self.changes = deque()

    def add(self, item):
        with self.__lock:
            self.__list.add(item)
        if item in self.changes:
            self.changes.remove(item)

    def sync_remove(self, item):
        # print('::sync_remove called :', item)
        with self.__lock:
            self.__list.discard(item)
            self.changes.appendleft(item)

    def discard(self, item, include_changes=True):
        with self.__lock:
            self.__list.discard(item)
            if include_changes:
                self.changes.appendleft(item)

    def pop(self):
        with self.__lock:
            return self.__list.pop()

    def copy(self):
        with self.__lock:
            return self.__list.copy()

    def clear(self):
        with self.__lock:
            self.__list.clear()

    def clear_changes(self):
        with self.__lock:
            self.changes.clear()

    def getchanges(self):
        # print('::getchanges called: ', self.changes)
        r = self.changes.copy()
        self.changes.clear()
        return r

    def __iter__(self):
        with self.__lock:
            return self.__list.__iter__()

    def __getitem__(self, index):
        with self.__lock:
            return self.__list.__getattribute__(index)

    def __len__(self):
        with self.__lock:
            return len(self.__list)

    def __str__(self):
        with self.__lock:
            return "[" + " ".join([str(i.id) for i in self.__list]) + "]"

    def __contains__(self, item):
        with self.__lock:
            return item in self.__list

    def __del__(self):
        with self.__lock:
            self.__list.clear()


class FileDict:
    __slots__ = '__continued', '__completed', '__current', '__lock'
    __annotations__ = {
        '__continued': dict,
        '__completed': dict,
        '__current': dict,
        '__lock': threading.Lock
    }

    def __init__(self):
        self.__continued = defaultdict(set)  # str: set[PeerFilePool]
        self.__completed = defaultdict(set)  # str: set[PeerFilePool]
        self.__current = defaultdict(set)  # str: set[PeerFilePool]
        self.__lock = threading.Lock()

    def add_to_current(self, _id, file_pool):
        with self.__lock:
            self.__current[_id].add(file_pool)

    def add_to_completed(self, _id, file_pool):
        with self.__lock:
            self.__current[_id].discard(file_pool)
            self.__completed[_id].add(file_pool)

    def add_to_continued(self, _id, file_pool):
        with self.__lock:
            self.__current[_id].discard(file_pool)
            self.__continued[_id].add(file_pool)

    def swap(self, _id, file_pool):
        with self.__lock:
            self.__continued[_id].remove(file_pool)
            self.__completed[_id].add(file_pool)

    @property
    def continued(self):
        with self.__lock:
            return self.__continued.values()

    @property
    def completed(self):
        with self.__lock:
            return self.__completed.values()

    @property
    def current(self):
        with self.__lock:
            return self.__current.values()
