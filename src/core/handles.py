import os
import struct
import socket
from abc import abstractmethod
from multiprocessing.managers import BaseProxy
from pathlib import Path

from src.avails import (
    connect,
    use,
)
from src.core.transfers import PeerFilePool


class TaskHandle:
    def __init__(self, handle_id):
        self._handle_id = handle_id
        self._result = None

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
    _exposed_ = ['status', 'result', 'chain', 'start', 'cancel', 'ident', '__getattribute__']

    def status(self, *args, **kwargs):
        return self._callmethod('status', *args, **kwargs)

    def result(self):
        return self._callmethod('result')

    def chain(self, file_list):
        return self._callmethod('chain', file_list)

    @property
    def ident(self):
        return self._callmethod('__getattribute__', ('_handle_id',))

    def start(self):
        return self._callmethod('start')

    def cancel(self):
        return self._callmethod('cancel')


class FileTaskHandle(TaskHandle):
    def __init__(self, handle_id, file_list, files_id, connection: connect.Socket, function_code):
        super().__init__(handle_id)
        # later converted into PeerFilePool in may be different Process
        self.file_pool = file_list
        self.files_id = files_id
        self.socket = connection
        self.function_code = function_code

    def start(self):
        use.echo_print('starting ', self.function_code, 'with', self.socket)  # debug
        self.file_pool = PeerFilePool(self.file_pool, _id=self.files_id)
        self._result = getattr(self.file_pool, self.function_code)(self.socket)
        print('completed file task', self._result)  # debug
        return self._handle_id, self._result

    def chain(self, file_list):
        # :todo complete chaining of extra files
        self.file_pool.add_continuation(file_list)

    def cancel(self):
        self.file_pool.stop()

    def status(self):
        ...

    def __str__(self):
        return self.ident.__str__() + ',' + self.file_pool.__str__() + ',' + self.socket.__str__() + ',' + id(self)
