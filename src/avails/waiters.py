from collections import namedtuple
from io import BufferedReader
from typing import BinaryIO, Callable

from functools import partial
import socket
import os
import src.avails.constants as const

type ThController = _ThreadControl


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


class Waits:

    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        pass


_ThreadControl = namedtuple('_ThreadControl', field_names=['control_flag', 'reader', 'select_waker', 'thread', 'flag_check'])


def get_thread_controller(control_flag, select_reader, select_waker, thread):
    def _is_set(event):
        return event.is_set()
    flag = partial(_is_set,control_flag)
    return _ThreadControl(control_flag, select_reader, select_waker, thread, flag)
