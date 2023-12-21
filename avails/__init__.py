import threading
from collections.abc import MutableSet
import time
import socket


class Fluxuant(MutableSet):
    def __init__(self):
        self._data = set()
        self._changes = set()  # Track changes since the last synchronization
        self._lock = threading.Lock()

    def add(self, item):
        with self._lock:
            self._data.add(item)
            self._changes.add(('1', item))

    def discard(self, item):
        with self._lock:
            self._data.discard(item)
            self._changes.add(('0', item))

    def get_changes(self):
        with self._lock:
            changes = list(self._changes)
            self._changes.clear()  # Clear the changes after synchronization
            return changes

    def __contains__(self, item):
        with self._lock:
            return item in self._data

    def __iter__(self):
        with self._lock:
            return iter(self._data)

    def __len__(self):
        with self._lock:
            return len(self._data)

    def __str__(self) -> str:
        return super().__str__()