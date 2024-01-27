import threading
import socket
import time
import json
import asyncio
import struct
from collections.abc import MutableSet

import avails.constants as const
from logs import errorlog
from logs import activitylog
from logs import serverlog
from avails.fileobject import PeerFile
from avails.remotepeer import RemotePeer
from avails.textobject import PeerText


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


class NotInUse(DeprecationWarning):
    """A class to denote deprecated/not currently used functions/methods/classes"""

    def __init__(self, *args, **kwargs):
        pass
