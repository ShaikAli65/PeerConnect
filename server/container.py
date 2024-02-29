import threading


class CustomSet:
    def __init__(self):
        self.__list = set()
        self.__lock = threading.Lock()
        self.__changes = set()
        self.removes = set()
        self.__clear = False

    def __iter__(self):
        return self.__list.__iter__()

    def __len__(self):
        return len(self.__list)

    def __str__(self):
        return " ".join([str(i) for i in self.__list])

    def __contains__(self, item):
        return item in self.__list

    def add(self, item):
        with self.__lock:
            self.__list.add(item)
            self.__changes.add(item)
            if item in self.removes:
                self.removes.discard(item)

    def removes(self, item):
        with self.__lock:
            self.__list.discard(item)
            self.removes.add(item)
            self.__changes.add(item)

    def discard(self, item):
        with self.__lock:
            self.__list.discard(item)
            self.removes.add(item)
            self.__changes.add(item)

    def pop(self):
        with self.__lock:
            item = self.__list.pop()
            self.removes.add(item)
            self.__changes.add(item)
            return item

    def copy(self):
        with self.__lock:
            return self.__list.copy()

    def clear(self):
        with self.__lock:
            self.__list.clear()
            self.__clear = True

    def changes(self):
        with self.__lock:
            changes = self.__changes
            self.__changes.clear()
            return changes

    def removedchanges(self):
        with self.__lock:
            changes = self.removes
            return changes

    def clearchanges(self):
        with self.__lock:
            self.removes.clear()

    def isclear(self):
        with self.__lock:
            return self.__clear
