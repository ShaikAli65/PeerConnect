import threading

from collections import deque, defaultdict


# from typing import ValuesView
# from .remotepeer import RemotePeer

class PeerDict(dict):
    __slots__ = '__lock',

    def __init__(self):
        super().__init__()
        self.__lock = threading.Lock()

    def get_peer(self, peer_id):  # -> RemotePeer:
        with self.__lock:
            return self.__getitem__(peer_id)

    def add_peer(self, peer_obj):  # RemotePeer):
        with self.__lock:
            self.__setitem__(peer_obj.id, peer_obj)

    def remove_peer(self, peer_id):
        with self.__lock:
            return self.pop(peer_id, None)

    def peers(self):  # -> ValuesView[RemotePeer]:
        with self.__lock:
            return self.values()

    def clear(self):
        with self.__lock:
            self.clear()

    def __str__(self):
        return ', '.join(x.__repr__() for x in self.values())


class CustomSet:
    """
    CustomSet is a thread safe flip implementation with additional features.

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
        self.__continued = defaultdict(set)  # str: flip[PeerFilePool]
        self.__completed = defaultdict(set)  # str: flip[PeerFilePool]
        self.__current = defaultdict(set)  # str: flip[PeerFilePool]
        self.__lock = threading.Lock()

    def add_to_current(self, peer_id, file_pool):
        with self.__lock:
            self.__current[peer_id].add(file_pool)

    def add_to_completed(self, peer_id, file_pool):
        with self.__lock:
            self.__current[peer_id].discard(file_pool)
            self.__completed[peer_id].add(file_pool)

    def add_to_continued(self, peer_id, file_pool):
        with self.__lock:
            self.__current[peer_id].discard(file_pool)
            self.__continued[peer_id].add(file_pool)

    def swap(self, peer_id, file_pool):
        with self.__lock:
            self.__continued[peer_id].remove(file_pool)
            self.__completed[peer_id].add(file_pool)

    def get_running_file(self, peer_id, file_id):
        return next(file for file in self.__current[peer_id] if file.id == file_id)

    def get_completed_file(self, peer_id, file_id):
        return next(file for file in self.__completed[peer_id] if file.id == file_id)

    def get_continued_file(self, peer_id, file_id):
        return next(file for file in self.__continued[peer_id] if file.id == file_id)

    def get_file(self, peer_id, file_id):
        try:
            return self.get_running_file(peer_id, file_id)
        except StopIteration:
            pass
        try:
            return self.get_completed_file(peer_id, file_id)
        except StopIteration:
            pass
        try:
            return self.get_continued_file(peer_id, file_id)
        except StopIteration:
            pass
        return None

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

    def stop_all_files(self):
        with self.__lock:
            for file_set in self.__current.values():
                for file in file_set:
                    file.break_loop()
            self.__continued.update(self.__current)
            self.__current.clear()
        return
