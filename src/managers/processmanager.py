import abc
import functools
import itertools
import threading
import socket
import time
import json
import asyncio
import os
import multiprocessing
from multiprocessing.managers import BaseProxy, BaseManager
from multiprocessing.connection import wait

import weakref
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Union, Dict, Tuple, Any

from src.avails import DataWeaver, SimplePeerText, PeerFilePool
from src.avails import connect
from src.core import peer_list
from src.avails import const


class TaskHandle:

    @abstractmethod
    def start(self):
        return NotImplemented

    @abstractmethod
    def cancel(self):
        return NotImplemented

    @property
    def ident(self):
        return self._handle_id

    @ident.setter
    def ident(self, value):
        self._handle_id = value

    @abstractmethod
    def status(self):
        return NotImplemented

    def __call__(self):
        return self.start()


class TaskHandleProxy(BaseProxy):
    _exposed_ = ['status', 'result', 'chain', '__getattribute__']

    def status(self, *args, **kwargs):
        return self._callmethod('status', *args, **kwargs)

    def result(self):
        return self._callmethod('result')

    def __getattribute__(self, item):
        return self._callmethod('__getattribute__', item)

    def chain(self, file_list):
        return self._callmethod('chain', file_list)


class FileTaskHandle(TaskHandle):
    def __init__(self, file_list, files_id, connection: connect.Socket, function):
        # later converted into PeerFilePool in may be different Process
        self.file_pool = file_list
        self.files_id = files_id
        self.socket = connection
        self.function = function
        self._result = None
        self._handle_id = None

    def start(self):
        self.file_pool = PeerFilePool(self.file_pool, _id=self.files_id)
        self._result = getattr(self.file_pool, self.function)(self.socket)
        return self._result

    def chain(self, file_list):
        # :todo complete chaining of extra files
        self.file_pool.add_continuation(file_list)

    def cancel(self):
        self.file_pool.stop()

    def status(self):
        ...

    def __str__(self):
        return self.ident.__str__() + ',' + self.file_pool.__str__() + ',' + self.socket.__str__() + ',' + id(self)


class DirectoryTaskHandle(TaskHandle):

    def __init__(self, directory, connection):
        self.directory = directory
        self.connection = connection
        self._result = None
        self._handle_id = None

    def start(self):
        ...

    def cancel(self):
        ...

    def status(self):
        ...

    def chain(self):
        ...


class HandleRepr:
    __slots__ = 'handle_id', 'args', 'kwargs'

    def __init__(self, handle_id, *args, **kwargs):
        self.handle_id = handle_id
        self.args = args
        self.kwargs = kwargs


class ProcessManager(BaseManager):
    ...


FILE = 'FileTaskHandle'
DIRECTORY = 'DirectoryTaskHandle'
SEND_COMMAND = 'send_files'
RECEIVE_COMMAND = 'recv_files'


class ProcessControl:
    handle_classes = {
        FILE: FileTaskHandle,
        DIRECTORY: DirectoryTaskHandle,
    }
    processes = []
    handles = {}
    MAX_LOAD = const.MAX_LOAD

    def __init__(self,
                 task_q: multiprocessing.Queue,
                 result_q: multiprocessing.Queue,
                 handle_proxy_q: multiprocessing.Queue,
                 connection_pipe: multiprocessing.connection.PipeConnection):
        self.handles = {}
        self.manager = ProcessManager()
        self.thread_pool = ThreadPoolExecutor(max_workers=const.MAX_LOAD)
        self.load = 0
        self.ident = multiprocessing.current_process().ident
        self.id_factory = itertools.count()
        self.task_queue = task_q
        self.result_queue = result_q
        self.handle_proxy_queue = handle_proxy_q
        self.connection_pipe = connection_pipe

    def run(self):
        while self.load < self.MAX_LOAD:
            handle_detail = self.task_queue.get()
            handle = getattr(self.manager, handle_detail.handle_id)
            handle_proxy = handle(*handle_detail.args, **handle_detail.kwargs)
            self.load += 1
            self.handle_proxy_queue.put(handle_proxy)
            fut = self.thread_pool.submit(handle_proxy.start)
            self.handles[handle.ident] = (handle, fut)

    def check_results(self):
        ...


class ProcessStore:
    handle_classes = {
        FILE: FileTaskHandle,
        DIRECTORY: DirectoryTaskHandle,
    }

    processes = {}
    handles = {}
    MAX_LOAD = const.MAX_LOAD
    task_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()
    handle_proxy_return_queue = multiprocessing.Queue()
    id_factory = itertools.count()
    thread_pool = ThreadPoolExecutor(max_workers=const.MAX_LOAD)
    main_thread_load = 0


def submit(loop: asyncio.AbstractEventLoop, handle_code, *args, **kwargs):
    if ProcessStore.main_thread_load < ProcessStore.MAX_LOAD:
        # Execute in a thread
        handle_class = ProcessStore.handle_classes[handle_code]
        handle = handle_class(*args, **kwargs)
        handle_id = next(ProcessStore.id_factory)
        ProcessStore.handles[handle_id] = handle
        handle.ident = handle_id
        return handle, loop.run_in_executor(ProcessStore.thread_pool, handle)
    else:
        _check_process()
        ProcessStore.task_queue.put_nowait(HandleRepr(handle_code, *args, **kwargs))
        handle_proxy = ProcessStore.handle_proxy_return_queue.get(block=False)
        fut = asyncio.Future(loop=loop)
        ProcessStore.handles.update({handle_proxy.ident: (handle_proxy, fut)})
        return handle_proxy, fut


def _check_process():
    for process_proxy in ProcessStore.processes.values():
        if not process_proxy.is_full():
            break
    else:
        return _start_process()


def _start_process():
    connection_pipe, child_conn = multiprocessing.Pipe()
    process = multiprocessing.Process(
        target=_bootstrap_process_handle,
        args=(
            ProcessStore.task_queue,
            ProcessStore.result_queue,
            ProcessStore.handle_proxy_return_queue,
            child_conn,
        )
    )
    process.start()
    ProcessStore.processes[process.ident] = (process, connection_pipe)
    return process


def _bootstrap_process_handle(*process_args):
    process = ProcessControl(*process_args)
    process.run()


def get_handle(self, handle_id):
    """
    :returns handle: corresponding to the given handle_id
    or returns HandleProxy if the task is occuring in another process
    """
    return self.handles[handle_id]


def register_all():
    ProcessManager.register(FILE, FileTaskHandle, TaskHandleProxy)
    ProcessManager.register(DIRECTORY, DirectoryTaskHandle, TaskHandleProxy)
