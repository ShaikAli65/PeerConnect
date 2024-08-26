import itertools
import os
import pathlib
import struct
from abc import abstractmethod
from multiprocessing.managers import BaseProxy
from pathlib import Path

from src.avails import (
    connect,
    use,
    const,
    PeerFilePool,
    SimplePeerBytes,
    FileItem
)


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


class DirectoryTaskHandle(TaskHandle):
    chunk_size = 1024
    end_dir_with = '/'

    def __init__(self, handle_id, dir_path, dir_id, connection: connect.Socket, function_code):
        super().__init__(handle_id)
        self.dir_path = dir_path
        self.dir_id = dir_id
        self.socket = connection
        self.function_code = function_code
        self.dir_iterator = self.dir_path.rglob('*')
        self.current_file = None

    def start(self):
        # use.echo_print('starting ', self.function_code, 'with', self.socket)
        ...

    def pause(self):
        self.dir_iterator = itertools.chain([self.current_file], self.dir_iterator)

    def __send_dir(self):
        for item in self.dir_iterator:
            if item.is_file():
                if not self.__send_file(item):
                    self.pause()
                    break
            elif item.is_dir():
                if not any(item.iterdir()):
                    use.echo_print("sending empty dir:", self.__send_path(item, self.dir_path.parent, self.end_dir_with))
                    continue

    def __send_file(self, item_path: pathlib.Path):
        s = self.__send_path(item_path, self.dir_path.parent, None)
        self.socket.send(struct.pack('!Q', item_path.stat().st_size))
        with item_path.open('rb') as f:
            f_read = f.read
            while True:
                chunk = memoryview(f_read(self.chunk_size))
                if not chunk:
                    break
                self.socket.send(chunk)
                # progress.update(len(chunk))
        # progress.close()
        return s

    def __send_path(self, path: Path, parent, end_with):
        path = path.relative_to(parent)
        final_path = (path.as_posix() + end_with).encode(const.FORMAT)
        SimplePeerBytes(self.socket, final_path).send_sync()
        return final_path.decode(const.FORMAT)

    def recv_dir(self):
        while True:
            path = SimplePeerBytes(self.socket)
            if not path.receive_sync():
                print("I am done")
                return
            rel_path = str(path)
            abs_path = Path(const.PATH_DOWNLOAD, rel_path[:-1])
            if rel_path.endswith("/"):
                os.makedirs(abs_path, exist_ok=True)
                continue
            os.makedirs(abs_path.parent, exist_ok=True)
            # print("parent", abs_path.parent)
            # print("got path", rel_path)
            self.recv_file(abs_path)
            # print("received file", f_size)

    def recv_file(self, file_path):
        size = self.socket.recv(8)
        file_item = FileItem(size, file_path, 0)

        ...

    def cancel(self):
        ...

    def status(self):
        ...

    def chain(self):
        ...
