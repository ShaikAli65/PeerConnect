import os
import socket
import threading

from io import BufferedReader
from typing import BinaryIO, Callable, Union
from functools import partial

import src.avails.constants as const

type ThController = ThreadController


def waker_flag() -> tuple[BufferedReader | BinaryIO, Callable]:
    """
    This function is made to pass in a file descriptor to (sort of trojan horse) select module primitives
    which prevents polling and waking up of cpu in regular intervals
    On Windows system this function returns a pair of socket file descriptors connected to each other providing pipe-like
    behaviour
    as select on windows does not support file descriptors
    other that sockets
    On other platforms this function returns a ~os.pipe's file descriptors wrapped in TextIOWrapper
    :return:pair of `BufferedReader | BinaryIO, a function which writes to reader` on calling
    """

    def _write(to_write):
        to_write.write(b'x')
        to_write.flush()

    if const.WINDOWS:
        w_sock, r_sock = socket.socketpair()
        read = r_sock.makefile('rb')
        write = partial(_write, w_sock.makefile('wb'))
        r_sock.close()
        w_sock.close()
    else:
        r_file, w_file = os.pipe()
        read = os.fdopen(r_file, 'rb')
        write = partial(_write, os.fdopen(w_file, 'wb'))

    return read, write


# namedtuple('_ThreadControl', field_names=['control_flag', 'reader', 'select_waker', 'thread', 'proceed'])
class ThreadController:
    """

        This is used to control threads in a blocking way
        this object can be called directly to wake ~select.select calls instantly
        which were blocked in order to get their reads active
        control_flag: threading.Event
        reader: BufferedReader | BinaryIO
        select_waker: Callable
        thread: threading.Thread

    """
    __slots__ = 'control_flag', 'reader', 'select_waker', 'thread'
    __annotations__ = {
        'control_flag': Union[threading.Event, bool],
        'reader': BufferedReader | BinaryIO,
        'select_waker': Callable,
        'thread': threading.Thread
    }

    def __init__(self, thread, control_flag=None):
        self.control_flag = control_flag or threading.Event()
        self.reader, self.select_waker = waker_flag()
        self.thread = thread

    def __call__(self):
        self.stop()

    def set(self):
        """
        This function sets the underlying control flag Event
        useful when to_stop is used in a while loop which prevent inverting True to False and vice versa
        :return:
        """
        self.control_flag.set()

    @property
    def to_stop(self):
        return self.control_flag.is_set()

    def stop(self):
        if self.control_flag.is_set():
            self.control_flag.set()
        else:
            self.control_flag.clear()

        self.select_waker()
        if self.thread:
            self.thread.join()
        self.reader.flush()

    def fileno(self):
        return self.reader.fileno()
