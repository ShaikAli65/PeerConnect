import os
import socket

from io import BufferedReader, BufferedWriter
from typing import BinaryIO
from . import const


def _waker_flag_windows():
    """
    This function is made to pass in a file descriptor to (sort of trojan horse) select module primitives
    which prevents polling and waking up of cpu in regular intervals
    On Windows system this function returns a pair of socket file descriptors connected to each other providing pipe-like
    behaviour
    as select on windows does not support file descriptors other than sockets

    On other platforms this function returns a ~os.pipe's file descriptors wrapped in TextIOWrapper
    :return:pair of `BufferedReader | BinaryIO, a function which writes to reader` on calling
    """
    w_sock, r_sock = socket.socketpair()
    w_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 0x2)
    r_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 0x2)
    read = r_sock.makefile('rb')
    write = w_sock.makefile('wb')
    # write = partial(_write, w_sock.makefile('wb'))
    r_sock.close()
    w_sock.close()
    return read, write


def _waker_flag_linux():
    """
    This function is made to pass in a file descriptor to (sort of trojan horse) select module primitives
    which prevents polling and waking up of cpu in regular intervals
    On Windows system this function returns a pair of socket file descriptors connected to each other providing pipe-like
    behaviour
    as select on windows does not support file descriptors other that sockets
    On other platforms this function returns a ~os.pipe's file descriptors wrapped in TextIOWrapper
    :return:pair of `BufferedReader | BinaryIO, a function which writes to reader` on calling
    """

    r_file, w_file = os.pipe()
    read = os.fdopen(r_file, 'rb')
    # write = partial(_write, os.fdopen(w_file, 'wb'))
    write = os.fdopen(w_file, 'wb')
    return read, write


# setting these dynamically at importing stage to reduce condition checking inside functions
if const.WINDOWS:
    _waker_flag = _waker_flag_windows
else:
    _waker_flag = _waker_flag_linux


# namedtuple('_ThreadControl', field_names=['control_flag', 'reader', 'select_waker', 'thread', 'proceed'])
# changed to specialized class

class _ThreadActuator:
    """

        This is used to control threads in a blocking way
        :func:`signal_stopping` can be used directly to wake ~select.select calls instantly
        which were blocked in order to get their reads active
        can be used directly in condition checking to check for
        control_flag: threading.Event
        reader: BufferedReader | BinaryIO
        select_waker: Callable
        thread: threading.Thread

    """
    __slots__ = 'control_flag', 'reader', 'waker',

    __annotations__ = {
        'control_flag': bool,
        'reader': BufferedReader | BinaryIO,
        'select_waker': BufferedWriter | BinaryIO,
    }

    def __init__(self):
        self.control_flag = False
        self.reader, self.waker = _waker_flag()

    def wake(self):
        self.waker.write(b'\x00')
        self.waker.flush()

    def flip(self):
        """
        This function sets or unsets the underlying control flag Event
        useful when to_stop is used in a while loop which prevent inverting True to False and vice versa
        :return:
        """
        self.control_flag = not self.control_flag

    @property
    def to_stop(self):
        return self.control_flag

    def clear_reader(self):
        self.reader.read(1)

    def signal_stopping(self):
        self.flip()
        self.wake()
        self.clear_reader()

    def fileno(self):
        return self.reader.fileno()

    def __bool__(self):
        return self.control_flag

    def __str__(self):
        # return f"<ThreadActuator(set={self.control_flag.is_set()})>"
        return f"<ThreadActuator(set={self.control_flag})>"

    def __repr__(self):
        return self.__str__()


Actuator = _ThreadActuator


__all__ = (
    'Actuator',
)
