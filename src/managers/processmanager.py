import asyncio
import itertools
import logging
import multiprocessing
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from multiprocessing.connection import wait
from multiprocessing.managers import BaseManager

from src.avails import (
    Actuator,
    const,
    use
)
from src.avails.handles import DirectoryTaskHandle, FileTaskHandle, TaskHandleProxy


class HandleRepr:  # :todo try this using named tuple
    __slots__ = 'handle_code', 'args', 'kwargs'

    def __init__(self, handle_code, *args, **kwargs):
        self.handle_code = handle_code
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        return '<HandleRepr(' + str(self.handle_code) + ', ' + str(self.args) + str(self.kwargs) + ') >'


class ProcessManager(BaseManager):
    ...


FILE = 'FileTaskHandle'
DIRECTORY = 'DirectoryTaskHandle'
SEND_COMMAND = 'send_files'
RECEIVE_COMMAND = 'recv_files'

COLORS = [
    "\033[91m",  # Red
    "\033[92m",  # Green
    "\033[93m",  # Yellow
    "\033[94m",  # Blue
    "\033[95m",  # Magenta
]

COLOR_RESET = "\033[0m"


class ProcessControl:
    handle_classes = {
        FILE: FileTaskHandle,
        DIRECTORY: DirectoryTaskHandle,
    }
    processes = []
    handles = {}
    MAX_LOAD = const.MAX_LOAD

    def __init__(self,
                 load: multiprocessing.Value,
                 task_q: multiprocessing.Queue,
                 result_q: multiprocessing.Queue,
                 handle_proxy_q: multiprocessing.Queue,
                 connection_pipe: multiprocessing.connection.Connection,
                 print_lock: multiprocessing.Lock,
                 ):
        self.handles = {}
        self.manager = ProcessManager()
        self.manager.start()
        self.thread_pool = ThreadPoolExecutor(max_workers=const.MAX_LOAD)
        self.load = load
        self.ident = multiprocessing.current_process().ident
        self.id_factory = itertools.count()
        self.proceed = True
        # self.task_wait_check = Actuator()
        self.task_wait_check = threading.Event()

        self.task_queue = task_q
        self.result_submission_queue = result_q
        self.handle_proxy_queue = handle_proxy_q
        self.connection_pipe = connection_pipe

        self.std_color = COLORS[self.ident % 5]
        self.print_lock = print_lock

    def run(self):
        while self.proceed:
            self.__load_check()
            handle_detail = self.task_queue.get()
            if handle_detail is None:
                return
            self.print_debugs('received task:', handle_detail)  # debug
            handle = getattr(self.manager, handle_detail.handle_code)
            # this returns corresponding proxy class from manager
            handle_proxy = handle(f'{self.ident}/{next(self.id_factory)}', *handle_detail.args, **handle_detail.kwargs)
            self.load.value += 1
            self.handle_proxy_queue.put(handle_proxy)
            fut = self.thread_pool.submit(handle_proxy.start)
            fut.add_done_callback(self.submit_result)
            self.handles[handle_proxy.ident] = (handle_proxy, fut)

    def submit_result(self, future):
        self.print_debugs('completed execution',future.result())  # debug
        self.result_submission_queue.put((future.result()))
        self.load.value -= 1
        self.may_be_trigger_task_receiver()

    def may_be_trigger_task_receiver(self):
        if self.load.value >= self.MAX_LOAD:
            self.task_wait_check.set()
            self.task_wait_check.clear()

    def stop(self):
        self.proceed = False
        self.task_wait_check.clear()

    def print_debugs(self, *args):
        with self.print_lock:
            print(self.std_color, f'[PID:{self.ident}]', *args, COLOR_RESET)

    def __load_check(self):
        self.print_debugs('checking load:', self.load)  # debug
        if self.load.value >= self.MAX_LOAD:
            self.print_debugs('load exceeded waiting for getting emptied')  # debug
            # select([self.task_wait_check], [], [])
            self.task_wait_check.wait()
            self.print_debugs('waiting for getting emptied')  # debug
        self.print_debugs('found load free')


def result_watcher(result_queue:multiprocessing.Queue, handle_references: dict):
    while True:
        result = result_queue.get()
        if result is None:
            break
        handle_identifier, result = result
        handle_proxy, fut = handle_references[handle_identifier]
        use.echo_print('got result in watcher result={', result,'}from handle id : ', handle_identifier)  # debug
        fut.set_result(result)


class ProcessStore:
    handle_classes = {
        FILE: FileTaskHandle,
        DIRECTORY: DirectoryTaskHandle,
    }
    processes = {}
    handles = {}
    _handle_lock = threading.Lock()
    main_thread_load = 0
    _load_lock = threading.Lock()
    # MAX_LOAD = const.MAX_LOAD
    MAX_LOAD = 3
    task_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()
    handle_proxy_return_queue = multiprocessing.Queue()
    print_lock = multiprocessing.Lock()
    id_factory = itertools.count()
    thread_pool = ThreadPoolExecutor(max_workers=MAX_LOAD)
    to_stop = Actuator()
    result_watcher = threading.Thread(target=result_watcher, args=(result_queue, handles), daemon=True)
    result_watcher.start()

    @classmethod
    def increment_load(cls):
        with cls._load_lock:
            cls.main_thread_load += 1

    @classmethod
    def decrement_load(cls, *args, **kwargs):
        with cls._load_lock:
            cls.main_thread_load -= 1

    @classmethod
    def add_handle(cls, handle_id, handle):
        with cls._handle_lock:
            cls.handles.update({handle_id: handle})

    @classmethod
    def get_handle(cls, handle_id):
        with cls._handle_lock:
            return cls.handles.get(handle_id, None)


def submit(loop: asyncio.AbstractEventLoop, handle_code, *args, **kwargs):
    use.echo_print('main process id :', os.getpid(), multiprocessing.current_process())
    use.echo_print('got a submission request for ', handle_code, "with args", args, kwargs)  # debug
    if ProcessStore.main_thread_load < ProcessStore.MAX_LOAD:
        # Execute in a thread
        ProcessStore.increment_load()
        use.echo_print('found main thread free, load::', ProcessStore.main_thread_load)  # debug
        handle_class = ProcessStore.handle_classes[handle_code]
        handle_id = next(ProcessStore.id_factory)
        handle = handle_class(handle_id, *args, **kwargs)
        handle.ident = handle_id
        ProcessStore.add_handle(handle_id, handle)
        use.echo_print('running in executor')  # debug
        fut = loop.run_in_executor(ProcessStore.thread_pool, handle)
        fut.add_done_callback(ProcessStore.decrement_load)
        return handle, fut
    else:
        _check_process()
        # go with a process execution
        ProcessStore.task_queue.put_nowait(HandleRepr(handle_code, *args, **kwargs))
        handle_proxy = ProcessStore.handle_proxy_return_queue.get()
        f = Future()
        fut = asyncio.wrap_future(f, loop=loop)
        ProcessStore.add_handle(handle_proxy.ident, (handle_proxy, f))
        return handle_proxy, fut


def _check_process():
    for _, load, _ in ProcessStore.processes.values():
        if load.value < ProcessStore.MAX_LOAD:
            break
    else:
        use.echo_print('main thread load full, spawning a process')  # debug
        return _start_process()


def _start_process():
    connection_pipe, child_conn = multiprocessing.Pipe()
    load = multiprocessing.Value('i', 0)
    process = multiprocessing.Process(
        target=_bootstrap_process_handle,
        args=(
            load,
            ProcessStore.task_queue,
            ProcessStore.result_queue,
            ProcessStore.handle_proxy_return_queue,
            child_conn,
            ProcessStore.print_lock,
        )
    )
    process.start()
    ProcessStore.processes.update({process.ident: (process, load, connection_pipe)})
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


def register_classes(manager=ProcessManager):
    manager.register(FILE, FileTaskHandle, TaskHandleProxy)
    manager.register(DIRECTORY, DirectoryTaskHandle, TaskHandleProxy)


multiprocessing.log_to_stderr(logging.DEBUG)
