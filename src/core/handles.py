from abc import ABC, abstractmethod
from multiprocessing.managers import BaseProxy


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


class FileTaskHandle(TaskHandle, ABC):
    pass
