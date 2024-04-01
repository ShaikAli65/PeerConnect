import threading

from collections import deque


class CustomSet:
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

    def discard(self, item,include_changes=True):
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
            return "["+" ".join([str(i.id) for i in self.__list])+"]"

    def __contains__(self, item):
        with self.__lock:
            return item in self.__list

    def __del__(self):
        with self.__lock:
            self.__list.clear()
