import functools
import itertools
import os
import pickle
import socket
import struct
import sys
from math import isclose
from pathlib import Path
from typing import Iterator, Self
from typing import Union

import select
import tqdm

from src.avails import (
    Actuator,
    const,
    use,
)


def stringify_size(size):
    sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    index = 0
    while size >= 1024 and index < len(sizes) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {sizes[index]}"


class _FileItem:
    __annotations__ = {
        'name': str,
        'size': int,
        'path': Union[str | Path],
        'seeked': int,
        'ext': str,
    }
    __slots__ = 'name', 'size', 'path', 'seeked', 'ext'

    def __init__(self, size, path, seeked):
        name, self.ext = os.path.splitext(path)
        self.name = os.path.basename(name) + self.ext
        self.size = size
        self.path = path
        self.seeked = seeked

    def __str__(self):
        size_str = stringify_size(self.size)
        name_str = f"...{self.name[-20:]}" if len(self.name) > 20 else self.name

        str_str = f"_FileItem({name_str}, {size_str}, {self.path[:10]}{'...' if len(self.path) > 10 else ''})"
        # str_str = f"_FileItem({name_str}, {size_str}, {self.path})"
        return str_str
        # return f'{self.name}'

    def serialize(self, receiver_sock):
        obj = pickle.dumps(self)
        size = struct.pack('!I', len(obj))
        receiver_sock.send(size)
        receiver_sock.send(obj)

    @classmethod
    def deserialize(cls, sender_sock) -> Self:
        """
        Factory method which returns un pickled `_FileItem` from socket
        """
        raw_length = sender_sock.recv(4)
        length_to_recv = struct.unpack('!I', raw_length)
        data = sender_sock.recv(length_to_recv)
        return pickle.loads(data)

    def __repr__(self):
        return (f"_FileItem({self.name[:10]}, "  # {'...' if len(self.name) > 10 else ''}
                f"size={self.size}, "
                # f" {self.path[:10]}{'...' if len(self.path) > 10 else ''})")
                f'seeked={self.seeked})')
        # return f'{self.name}'

    def __iter__(self):
        return iter((self.name, self.size, self.path))

    def __getitem__(self, item):
        return (self.name, self.size, self.path)[item]


if sys.version_info >= (3, 12):
    from typing import TypeAlias

    FileItem: TypeAlias = _FileItem
else:
    FileItem = _FileItem


class PeerFilePool:
    retries = 8
    chunk_size = 1024 * 512,

    __slots__ = 'file_items', 'to_stop', '__error_extension', 'id', 'current_file', 'file_count'

    def __init__(self,
                 file_items: list[_FileItem] = None, *,
                 _id,
                 actuator: Actuator = None,
                 error_ext='.invalid',
                 ):

        self.to_stop = actuator or Actuator()
        self.to_stop.flip()
        # setting event thus reducing ~not'ting~ of self.proceed() in most of the loop checkings
        self.__error_extension = error_ext
        self.file_items: set[_FileItem] = set(file_items or [])
        self.id = _id
        self.current_file: Iterator[_FileItem] | _FileItem = self.file_items.__iter__()
        # this can be _FileItem() while recieving pointing to currently receiving file item
        # (we don't use ~self.file_items as list in case of receiving because it's redundent two store files details both ways)
        # and iterator while sending
        self.file_count = len(self.file_items)

    def send_files(self, receiver_sock):
        receiver_sock.setblocking(False)

        raw_file_count = struct.pack('!I', self.file_count)
        # print("sent file count ", raw_file_count)  # debug
        receiver_sock.send(raw_file_count)

        self.current_file, iterator = itertools.tee(self.file_items)
        # 1 iterator which gets forwarded after successful sending of current file
        # 2 iterator to proceed with for loop
        return self.send_file_loop(iterator, receiver_sock)

    def send_file_loop(self, current_iter, receiver_sock):
        for file in current_iter:
            if self.to_stop or self.__send_file(receiver_sock, file=file) is False:
                return False
            next(self.current_file)
        return True

    def __send_file(self, receiver_sock, file: _FileItem):
        file.serialize(receiver_sock)
        send_progress = tqdm.tqdm(
            range(file.size),
            f"::sending {file.name[:17] + '...' if len(file.name) > 20 else file.name} ",
            unit="B",
            unit_scale=True,
            unit_divisor=1024
        )

        result = self.__send_actual_file(receiver_sock, file, send_progress)
        send_progress.close()
        return result

    def __send_actual_file(self, receiver_sock, file, send_progress):
        sock_send = receiver_sock.send
        send_progress.update(file.seeked)
        back_off = use.get_timeouts(max_retries=self.retries)
        chunk_size = self.calculate_chunk_size(file.size)
        wait_sock_write = functools.partial(use.wait_for_sock_write, receiver_sock, self.to_stop)

        with open(file.path, 'rb') as f:
            f_read = f.read
            f.seek(file.seeked)
            seek = file.seeked
            while self.to_stop:
                chunk = memoryview(f_read(chunk_size))
                if not chunk:
                    break
                try:
                    sock_send(chunk)  # possible: connection reset err
                except BlockingIOError:
                    try:
                        wait_sock_write(next(back_off))
                        continue
                    except StopIteration:
                        file.seeked = seek  # can be ignored mostly for now
                        return False
                except ConnectionResetError:
                    break
                send_progress.update(len(chunk))
                seek += len(chunk)

        file.seeked = seek  # can be ignored mostly for now
        return True

    def recv_files(self, sender_sock: socket.socket):
        sender_sock.setblocking(False)

        reads = use.wait_for_sock_read(sender_sock, self.to_stop, 10)
        if self.to_stop in reads:
            use.echo_print("returning from receiving files actuator signalled")
            return
        if sender_sock not in reads:
            return
        raw_file_count = sender_sock.recv(4) or b'\x00\x00\x00\x00'
        self.file_count = struct.unpack('!I', raw_file_count)[0]
        print("received file count", self.file_count)  # debug
        return self.__receive_file_loop(self.file_count, sender_sock)

    def __receive_file_loop(self, count, sender_sock):
        for _ in range(count):
            if not self.to_stop:
                return
            if self.__recv_file(sender_sock) is False:
                return
            print("completed receiving", self.current_file)  # debug
            self.file_count -= 1
        return True

    def __recv_file(self, sender_sock):
        file_item = _FileItem.deserialize(sender_sock)
        file_item.name = self.__validatename(file_item.name)
        file_item.path = os.path.join(const.PATH_DOWNLOAD, file_item.name)
        progress = tqdm.tqdm(
            range(file_item.size),
            f"::receiving {file_item.name[:17] + '...' if len(file_item.name) > 20 else file_item.name} ",
            unit="B",
            unit_scale=True,
            unit_divisor=1024
        )
        self.current_file = file_item
        what = self.__recv_actual_file(sender_sock, file_item, progress)
        progress.close()
        return what

    def __recv_actual_file(self, sender_sock, file_item: _FileItem, progress):
        mode = 'xb' if file_item.seeked == 0 else 'rb+'  # if seeked == 0 that means we need to create file newly
        chunk_size = self.calculate_chunk_size(file_item.size)
        back_off = use.get_timeouts(max_retries=self.retries)
        wait_sock_read = functools.partial(use.wait_for_sock_read, sender_sock, self.to_stop)
        try:
            with open(file_item.path, mode) as file:
                f_write, f_recv, size = file.write, sender_sock.recv, file_item.size
                file.seek(file_item.seeked)
                progress.update(file_item.seeked)
                while self.to_stop and size > 0:
                    try:
                        data = f_recv(min(chunk_size, size))
                    except ConnectionResetError:
                        break
                    except BlockingIOError:
                        try:
                            wait_sock_read(next(back_off))
                            continue
                        except StopIteration:
                            return False

                    if not data:
                        break
                    f_write(data)  # possible: No Space Left
                    size -= len(data)
                    progress.update(len(data))
        finally:
            file_item.seeked = file_item.size - size
            if size > 0:
                self._add_error_ext(file_item)
                return False
        return True

    def send_files_again(self, receiver_sock):
        self.current_file, present_iter = itertools.tee(self.current_file)  # cloning iterators

        # -> ----------------------
        start_file = next(present_iter)
        reads, _, _ = select.select([receiver_sock, self.to_stop], [], [], 30)
        if receiver_sock not in reads:
            print("SOMETHING WRONG IN RECEIVING FILE SEEK", reads)
            return
        start_file.seeked = struct.unpack('!Q', receiver_sock.recv(8))[0]
        progress = tqdm.tqdm(range(start_file.size), f"::sending {start_file.name[:20]} ... ", unit="B",
                             unit_scale=True, unit_divisor=1024)
        self.__send_actual_file(receiver_sock, start_file, progress)
        progress.close()
        # -> ---------------------- file continuation part

        self.send_file_loop(present_iter, receiver_sock)
        return True

    def receive_files_again(self, sender_sock):
        # -> ----------------------
        start_file = self.current_file
        sender_sock.send(start_file.seeked)
        progress = tqdm.tqdm(range(start_file.size), f"::receiving {start_file.name[:20]} ... ", unit="B",
                             unit_scale=True, unit_divisor=1024)
        what = self.__recv_actual_file(sender_sock, start_file, progress)
        if not what:
            use.echo_print('got error again returning')  # debug
            progress.close()
            return
        self._remove_error_ext(start_file)
        # -> ---------------------- file continuation part

        self.__receive_file_loop(self.file_count, sender_sock)
        return True

    def _add_error_ext(self, file_item: _FileItem):
        """
            Handles file error by renaming the file with an error extension.
        """
        pathed = Path(file_item.path)
        file_name = self.__validatename(file_item.name + self.__error_extension)
        new_path = os.path.join(const.PATH_DOWNLOAD, file_name)
        pathed.rename(new_path)
        file_item.path = new_path
        file_item.name = file_name
        return file_item

    def _remove_error_ext(self, file_item: _FileItem):
        """
            Removes file error ext by renaming the file with its actual file extension .
        """
        pathed = Path(file_item.path)
        new_name = self.__validatename(pathed.stem)
        pathed.rename(os.path.join(const.PATH_DOWNLOAD, new_name))
        file_item.path = str(pathed)

    @staticmethod
    def __validatename(file_name):
        """
            Ensures a unique filename if a file with the same name already exists
            in `const.PATH_DOWNLOAD` directory.

            Args:
                file addr (str): The original filename.

            Returns:
                str: The validated filename, ensuring uniqueness.
        """
        base, ext = os.path.splitext(file_name)
        counter = 1
        new_file_name = file_name
        while os.path.exists(os.path.join(const.PATH_DOWNLOAD, new_file_name)):
            new_file_name = f"{base}({counter}){ext}"
            counter += 1
        return new_file_name

    @use.NotInUse
    def __chunkify(self, file_path, chunk_size):
        with open(file_path, 'rb') as file:
            f_read = file.read
            while self.to_stop:
                chunk = memoryview(f_read(chunk_size))
                if not chunk:
                    return
                yield chunk

    def __repr__(self):
        """
            Returns the file details
        """
        return f"_PeerFile(paths={self.file_items.__repr__()})"

    def __iter__(self):
        """
        :returns Internal file_paths list's iterator :
        """
        return self.file_items.__iter__()

    def reset(self):
        self.to_stop = Actuator()
        self.to_stop.flip()
        self.current_file: Iterator[_FileItem] | _FileItem = self.file_items.__iter__()
        self.file_count = 0

    def stop(self):
        self.to_stop.signal_stopping()

    @staticmethod
    def calculate_chunk_size(file_size: int):
        min_buffer_size = 64 * 1024  # 64 KB
        max_buffer_size = (2 ** 20) * 2  # 2 MB

        min_file_size = 1024
        max_file_size = (2 ** 30) * 2  # 2 GB

        if file_size <= min_file_size:
            return min_buffer_size
        elif file_size >= max_file_size:
            return max_buffer_size
        else:
            # Linear scaling between min and max buffer sizes
            buffer_size = min_buffer_size + (max_buffer_size - min_buffer_size) * (file_size - min_file_size) / (
                    max_file_size - min_file_size)
        return int(buffer_size)


GROUP_MIN = 1
GROUP_MAX = 2


@use.NotInUse
class FileGroup:
    def __init__(self, files: list[_FileItem] = None, *, bandwidth=1024 * 1024 * 512, level: int):
        self.files = sorted(files, key=lambda x: x.size)
        self.grouped_files: list[list[_FileItem]] = []
        self.total_size = sum(x.size for x in files)
        self.bandwidth = bandwidth
        self.grouping_level = level
        self.part_size = self.total_size // 6

    def group(self):
        self.part_size = self._adjust_part_size()
        parts = [[]]
        current_part_size = 0

        for file in self.files:
            file_size = file.size

            if current_part_size + file_size <= self.part_size or \
                    isclose(current_part_size + file_size, self.part_size, rel_tol=0.004):
                parts[-1].append(file)
                current_part_size += file_size
                continue
            if file_size >= 2 ** 30 or isclose(file_size, 2 ** 30, rel_tol=0.0002):  # check again ??
                parts.append([file])
                current_part_size = 0
            else:
                parts.append([file])
                current_part_size = file_size

        self.grouped_files = [x for x in parts if x]

        if len(self.grouped_files) > self.grouping_level:
            self.re_group(self.grouping_level)

    def _adjust_part_size(self):
        # if self.grouping_level == GROUP_MIN:
        #     return self.total_size // 2
        # if self.grouping_level == GROUP_MAX:
        #     return self.total_size // 6
        # if self.grouping_level == GROUP_MID:
        #     return self.total_size // 4
        return self.total_size // self.grouping_level

    def re_group(self, size):
        """Re-groups the files into the specified number of parts."""
        new_group = []
        combined_group = []
        total_size = 0

        for part in self.grouped_files:
            part_size = sum(file.size for file in part)
            if total_size + part_size <= self.part_size * size:
                combined_group.extend(part)
                total_size += part_size
            else:
                new_group.append(combined_group)
                combined_group = part
                total_size = part_size

        if combined_group:
            new_group.append(combined_group)

        self.grouped_files = new_group

    def __len__(self):
        return self.grouped_files.__len__()

    def __iter__(self):
        return self.grouped_files.__iter__()

    def __str__(self):
        string = (f'total size: {stringify_size(self.total_size)}\t'
                  f'total no.of files: {len(self.files)}\t'
                  f'part size : {stringify_size(self.part_size)}\n')

        parts_str = "\n".join(
            f"{stringify_size(sum(file.size for file in part))} : {part}" for part in self.grouped_files)

        return string + parts_str

    def __repr__(self):
        return f'_FileGroup(files={self.files.__repr__()})'
