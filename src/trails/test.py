import os.path
import socket
from typing import Any

import tqdm
from pathlib import Path
import tempfile

from src.avails import useables
from src.core import *
from src.avails.textobject import SimplePeerText  # , DataWeaver
from src.managers import filemanager  # , error_manager

type _Name = str
type _Size = int
type _FilePath = Union[str, Path]
type _FileItem = Tuple[_Name, _Size, _FilePath]
type FiLe = _PeerFile

FILE_NAME = 0
FILE_SIZE = 1
FILE_PATH = 2
CONNECT_SENDER = 3
CONNECT_RECEIVER = 4


class _PeerFile:

    def __init__(self,
                 paths: list[_FileItem] = None, *,
                 control_flag: threading.Event = threading.Event(),
                 chunk_size: int = 1024 * 512,
                 error_ext: str = '.invalid'
                 ):

        self.__control_flag = control_flag
        self.__control_flag.set()

        self.__chunk_size = chunk_size
        self.__error_extension = error_ext
        self.file_paths: list[_FileItem] = paths or list()
        if not paths:
            return

        for file_item in paths:
            file_path = file_item[FILE_PATH]
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_item}")

            if os.path.isdir(file_path):
                raise NotADirectoryError(f"Cannot use a directory in PeerFile: {file_path}")

            if not os.path.isfile(file_path):
                raise IsADirectoryError(f"Not a regular file: {file_path}")

    def __send_file(self, receiver_sock: socket.socket, *, file: _FileItem):
        """
           Accepts a connected socket as a parameter.
           Sends the file contents to the receiver.
              Does not provide error handling for the file transfer.
           Returns:
               bool: True if the file is sent successfully, False otherwise.
        """
        filename, file_size, file_path = file

        self.calculate_chunk_size(file_size)
        if not SimplePeerText(text=filename, refer_sock=receiver_sock).send():
            raise ValueError(f"Cannot send file_path :{filename} some error occurred")
        receiver_sock.send(struct.pack('!Q', file_size))

        # send_progress = tqdm.tqdm(range(file_size), f"::sending {filename[:20]} ... ", unit="B", unit_scale=True,
        #                           unit_divisor=1024)
        for data in self.__chunkify__(file_path):  # send the file in chunks
            receiver_sock.sendall(data)  # connection reset err
            # send_progress.update(len(data))
        # send_progress.close()

        return SimplePeerText(receiver_sock, text=const.CMD_FILE_SUCCESS, byte_able=False).send()

    def __recv_file(self, sender_sock: socket.socket):

        """
        Accepts a connected socket as a parameter.
        Receives the file contents from the sender and saves them with received data to Downloads/PeerConnect
            Adds that file path to the self. paths attribute of the class
            Does not provide error handling for the file transfer.
        Returns:
            bool: True if the file was received successfully, False otherwise.
        """

        filename = SimplePeerText(sender_sock).receive().decode(const.FORMAT)
        file_path = os.path.join(const.PATH_DOWNLOAD, self.__validatename__(filename))

        until_sock_is_readable(sender_sock, control_flag=self.__control_flag)
        file_raw_size = sender_sock.recv(8)

        if not len(file_raw_size) == 8:
            raise ValueError(f"Received file size buffer is not 8 bytes {file_raw_size}")

        file_size: int = struct.unpack('!Q', file_raw_size)[0]
        self.calculate_chunk_size(file_size)
        # progress = tqdm.tqdm(range(file_size), f"::receiving {filename[:20]}... ", unit="B", unit_scale=True,
        #                      unit_divisor=1024)
        self.file_paths.append((filename, file_size, file_path,))

        with open(file_path, 'wb') as file:
            while self.safe_stop and file_size > 0:
                # try:
                data = sender_sock.recv(min(self.__chunk_size, file_size))
                # error_manager.ErrorManager(error=err,......
                #       connectionspass
                file.write(data)  # possible : OSError errno 28 no space left
                # progress.update(len(data))
                file_size -= len(data)

        # progress.close()
        print()
        return SimplePeerText(refer_sock=sender_sock).receive(const.CMD_FILE_SUCCESS)

    def send_files(self, receiver_sock: socket.socket):
        """
        [
            (file_name, file_size, file_path),
        ]
        Sends all files in the list to the receiver.
        A connected socket is required as a parameter.
        Returns:
            bool: True if all files are sent successfully, False otherwise.
        """
        raw_file_count = struct.pack('!I', len(self.file_paths))
        receiver_sock.send(raw_file_count)
        progress = tqdm.tqdm(self.file_paths, f"::sending files... ", unit=" files")
        for file in self.file_paths:
            if not self.__send_file(receiver_sock, file=file):
                progress.close()
                return False
            progress.update(1)
        progress.close()
        return True

    def recv_files(self, sender_sock: socket.socket):
        """
        Receives all files from the sender.
        A connected socket is required as a parameter.
        Returns:
            bool: True if all files are received successfully, False otherwise.
        """
        until_sock_is_readable(sender_sock, control_flag=self.__control_flag)
        raw_file_count = sender_sock.recv(4)
        file_count = struct.unpack('!I', raw_file_count)[0]

        progress = tqdm.tqdm(range(file_count), f"::receiving files... ", unit=" files")
        for _ in range(file_count):
            if not self.__recv_file(sender_sock):
                progress.close()
                return False
            progress.update(1)
        progress.close()
        return True

    def __file_error__(self, filename):
        """
            Handles file errors by renaming the file with an error extension.
        """
        os.rename(filename, filename + self.__error_extension)
        filename += self.__error_extension
        return filename

    def __chunkify__(self, file_path: str | Path):
        with open(file_path, 'rb') as file:
            while self.safe_stop and (chunk := file.read(self.__chunk_size)):
                yield chunk

    @classmethod
    def __validatename__(cls, file_addr: str) -> str:
        """
            Ensures a unique filename if a file with the same name already exists.

            Args:
                file addr (str): The original filename.

            Returns:
                str: The validated filename, ensuring uniqueness.
        """
        base, ext = os.path.splitext(file_addr)
        counter = 1
        new_file_name = file_addr
        while os.path.exists(os.path.join(const.PATH_DOWNLOAD, new_file_name)):
            new_file_name = f"{base}({counter}){ext}"
            counter += 1
        return new_file_name

    @classmethod
    def get_temp_file(cls):
        temp_file = tempfile.NamedTemporaryFile(mode='w+', prefix="peer_c", dir=const.PATH_DOWNLOAD, delete=False)
        return temp_file

    def __str__(self):
        """
            Returns the file details
        """
        return ""

    @property
    def safe_stop(self):
        return self.__control_flag.is_set()

    def break_loop(self):
        self.__control_flag.clear()
        self.__control_flag = None

    def calculate_chunk_size(self, file_size: int):
        min_buffer_size = 64 * 1024  # 64 KB
        max_buffer_size = 1024 * 1024 * 2  # 2 MB

        min_file_size = 1024
        max_file_size = 1024 * 1024 * 1024 * 10  # 10 GB

        if file_size <= min_file_size:
            return min_buffer_size
        elif file_size >= max_file_size:
            return max_buffer_size
        else:
            # Linear scaling between min and max buffer sizes
            buffer_size = min_buffer_size + (max_buffer_size - min_buffer_size) * (file_size - min_file_size) / (
                    max_file_size - min_file_size)
        self.__chunk_size = int(buffer_size)
        return self.__chunk_size


class _FileGroup:

    def __init__(self, *, files: list[_FileItem] = None, bandwidth: int = 1024 * 1024 * 512):
        self.files = files
        self.grouped_files: list[Tuple[_FileItem]] = [tuple(files[:(len(files)//2)]), tuple(files[(len(files)//2):])]
        # self.grouped_files: list[Tuple[_FileItem]] = [tuple(files)]
        self.bandwidth = bandwidth

    def group(self):
        """
        throughput :
        bandwidth  : highest speed x MB/s
        latency    : 2ms
        file size : y mb
        max no. of tuples = 6
        () :A files total size : n mb
        () :B files
        () :C files
        () :D files nth file n+1 next tuple

        Groups files for transfer based on network conditions and file properties.

        Returns:
        A list of tuples, where each tuple represents a group of filenames to be transferred together.
        [
        (file1.txt,file2.txt),
        (file3.txt,file4.txt),
        ]
      """
        pass

    def re_group(self, size: int):
        """

        :param size:
        :return:
        """
        new_group = self.grouped_files
        return new_group

    def __len__(self):
        return self.grouped_files.__len__()

    def __iter__(self):
        return self.grouped_files.__iter__()


class _SockGroup:
    def __init__(self, sock_count: int, *, control_flag: threading.Event = threading.Event()):
        self.sock_list: list[socket.socket] = []
        self.sock_count = sock_count
        control_flag.set()
        self.__control_flag = control_flag

    def get_sockets_from(self, connection_sock: socket.socket):
        for i in range(self.sock_count):

            connection_sock = until_sock_is_readable(connection_sock, control_flag=self.__control_flag)
            if connection_sock is None:
                return

            conn, _ = connection_sock.accept()

            if SimplePeerText(refer_sock=conn, text=const.SOCKET_OK, byte_able=False).send():
                self.sock_list.append(conn)

    def connect_sockets(self, sender_ip: Tuple[Any,...]):
        for i in range(self.sock_count):
            _sock = socket.socket(const.IP_VERSION, const.PROTOCOL)

            _sock.connect(sender_ip)
            if SimplePeerText(refer_sock=_sock).receive(cmp_string=const.SOCKET_OK):
                self.sock_list.append(_sock)

    def close(self):
        for sock in self.sock_list:
            try:
                sock.close()
            except socket.error:
                pass

    @property
    def safe_stop(self):
        return self.__control_flag.is_set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def  __del__(self):
        self.close()

    def __len__(self):
        return self.sock_list.__len__()

    def __iter__(self):
        return self.sock_list.__iter__()


def make_file_groups(file_list: list[_FilePath]) -> _FileGroup:
    """
    A factory function which
    converts given list of file paths into a program required format of LIST[tuple(NAME, SIZE, FULL_PATH)]
    then passes it into _FileGroup()
    generates groups by calling func `_FileGroup::group`

    :returns _FileGroup:
    :param file_list:
    """
    file_items = [(os.path.basename(file), os.path.getsize(file), os.path.abspath(file)) for file in file_list]
    grouped = _FileGroup(files=file_items)
    grouped.group()
    return grouped


def make_sock_groups(sock_count: int,*, connect_ip: tuple[Any, ...] = None, bind_ip: tuple[Any, ...] = None) -> _SockGroup:
    """
    This factory function blocks until required no. of socket-connections are not made
    Caller is responsible for closing of sockets returned by this function
    :param bind_ip:    if specified then function will attempt to bind to that ip and listen for
                       no. of connections specified by :param sock_count:
    :param sock_count: function gets number of sockets specified by this
    :param connect_ip: if this is specified then function will take a turn and get sock_count no. of sockets
                       after successful connection to :param connect_ip:
    :return _SockGroup:
    """

    if connect_ip:
        grouped_sock = _SockGroup(sock_count)
        grouped_sock.connect_sockets(connect_ip)
        return grouped_sock

    with socket.socket(const.IP_VERSION, const.PROTOCOL) as refer_sock:
        refer_sock.bind(bind_ip)
        refer_sock.listen(sock_count)
        grouped_sock = _SockGroup(sock_count)
        grouped_sock.get_sockets_from(refer_sock)
        return grouped_sock
