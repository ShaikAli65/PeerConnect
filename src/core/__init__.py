import threading
import socket
import time
import json
import asyncio
import struct
import select
import selectors
import os
from collections.abc import MutableSet
from typing import Union, Dict, Tuple

import src.avails.constants as const
from logs import error_log
from logs import activity_log
from logs import server_log


class NotInUse:
    __annotations__ = {
        'function': str,
        '__doc__': str
    }
    __slots__ = ('function', '__doc__')

    def __init__(self, function):
        """
        Decorator class to mark functions as not in use or not fully tested.
        :raises ValueError : if function gets called
        Args:
        - function: The function to be decorated.
        """
        self.__doc__ = """This class is used to mark functions that are not currently in use or haven't been fully tested.
        By marking a function with this class, it prevents the call to the function unless explicitly allowed by the user.
        """
        self.function = function

    def __call__(self, *args, **kwargs):
        """
        Args:
        - *args: Positional arguments for the function.
        - **kwargs: Keyword arguments for the function.
        """
        raise ValueError(f"Your are not supposed to call this function :{self.function.__name__}")


@NotInUse
class CustomDict:
    def __init__(self, **kwargs):
        self._data = dict(kwargs)
        self._lock = threading.Lock()

    def __getitem__(self, key):
        with self._lock:
            return self._data[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._data[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._data[key]

    def keys(self):
        with self._lock:
            return self._data.keys()

    def values(self):
        with self._lock:
            return self._data.values()

    def items(self):
        with self._lock:
            return self._data.items()

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def __str__(self):
        with self._lock:
            return str(self._data)

    def __repr__(self):
        with self._lock:
            return repr(self._data)

    def __iter__(self):
        with self._lock:
            return iter(self._data)

    def __next__(self):
        with self._lock:
            return next(self._data.__iter__())

    def __len__(self):
        with self._lock:
            return len(self._data)

    def __eq__(self, other):
        with self._lock:
            return self._data == other

    def __ne__(self, other):
        with self._lock:
            return self._data != other

    def __lt__(self, other):
        with self._lock:
            return self._data < other

    def __le__(self, other):
        with self._lock:
            return self._data <= other

    def __gt__(self, other):
        with self._lock:
            return self._data > other

    def __ge__(self, other):
        with self._lock:
            return self._data >= other

    def copy(self):
        with self._lock:
            return self._data.copy()

    def pop(self, key, default=None):
        with self._lock:
            return self._data.pop(key, default)

    def popitem(self):
        with self._lock:
            return self._data.popitem()

    def clear(self):
        with self._lock:
            self._data.clear()

    def update(self, *args, **kwargs):
        with self._lock:
            self._data.update(*args, **kwargs)

    def __contains__(self, key):
        with self._lock:
            return key in self._data

    def setdefault(self, key, default=None):
        with self._lock:
            return self._data.setdefault(key, default)

    @classmethod
    def fromkeys(cls, seq, value=None):
        return dict.fromkeys(seq, value)


def until_sock_is_readable(sock: socket.socket, *, control_flag: threading.Event):
    """
    Helper function, this function blocks until a socket is readable using `select.select` and timeout defaults to 0.01
    :param sock: socket to get ready
    :param control_flag: flag to end the loop, this function checks for func `threading.Event::is_set`
    :return: returns socket when it is readable ,returns None if the loop breaks through `threading.Event::is_set`
    """
    try:
        while control_flag.is_set():
            readable, _, _ = select.select([sock,], [], [], 0.01)
            if sock in readable:
                return sock
        else:
            return None
    except (select.error, ValueError):
        return None
