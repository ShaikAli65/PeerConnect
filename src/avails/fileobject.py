from typing import Any

from pathlib import Path
from math import isclose
from collections import namedtuple
import tqdm
import tempfile
from src.core import *
from src.avails.textobject import SimplePeerText

type _Name = str
type _Size = int
type _FilePath = Union[str, Path]
type FiLe = PeerFile

__FileItem = namedtuple('__FileItem', ['name', 'size', 'path'])


class _FileItem(__FileItem):
    @staticmethod
    def stringify_size(size: int) -> str:
        sizes = ['B', 'KB', 'MB', 'GB', 'TB']
        index = 0
        while size >= 1024 and index < len(sizes) - 1:
            size /= 1024
            index += 1
        return f"{size:.2f} {sizes[index]}"

    def __str__(self):
        size_str = self.stringify_size(self.size)
        name_str = f"...{self.name[-10:]}" if len(self.name) > 10 else self.name
        return f"file({name_str}, {size_str})"

    def __repr__(self):
        return self.__str__()


class PeerFile:

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
            file_path = file_item.path
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
        # print("sending :", file)
        self.calculate_chunk_size(file_size)
        if not SimplePeerText(text=filename, refer_sock=receiver_sock).send():
            raise ValueError(f"Cannot send file_path :{filename} some error occurred")
        receiver_sock.send(struct.pack('!Q', file_size))
        # print("sent size",file_size,self.__chunk_size,receiver_sock)

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

        filename = SimplePeerText(sender_sock)
        if not filename.receive():
            return
        filename = filename.decode()
        file_path = os.path.join(const.PATH_DOWNLOAD, self.__validatename__(filename))
        sender_sock = until_sock_is_readable(sender_sock, control_flag=self.__control_flag)
        file_raw_size = sender_sock.recv(8) if hasattr(sender_sock, "recv") else 0

        if not len(file_raw_size) == 8:
            raise ValueError(f"Received file size buffer is not 8 bytes {file_raw_size}")

        file_size: int = struct.unpack('!Q', file_raw_size)[0]
        self.calculate_chunk_size(file_size)
        # progress = tqdm.tqdm(range(file_size), f"::receiving {filename[:20]}... ", unit="B", unit_scale=True,
        #                      unit_divisor=1024)
        self.file_paths.append(_FileItem(filename, file_size, file_path, ))
        with open(file_path, 'xb') as file:
            while self.safe_stop and file_size > 0:
                # try:
                data = sender_sock.recv(min(self.__chunk_size, file_size))
                # error_manager.ErrorManager(error=err,......
                #       connections pass
                file.write(data)  # possible : OSError err no 28 (no space left)
                # progress.update(len(data))
                file_size -= len(data)

        # progress.close()
        return SimplePeerText(refer_sock=sender_sock).receive(const.CMD_FILE_SUCCESS)

    def send_files(self, receiver_sock: socket.socket):
        """
        [
            _FileItem(file_name, file_size, file_path),
        ]
        Sends all files in the list to the receiver.
        A connected socket is required as a parameter.
        Returns:
            bool: True if all files are sent successfully, False otherwise.
        """
        receiver_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, False)
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
        sender_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, False)
        sender_sock = until_sock_is_readable(sender_sock, control_flag=self.__control_flag)
        raw_file_count = sender_sock.recv(4) if hasattr(sender_sock, "recv") else b'\x00\x00\x00\x00'
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

    @staticmethod
    def __validatename__(file_addr: str) -> str:
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

    @staticmethod
    def get_temp_file():
        temp_file = tempfile.NamedTemporaryFile(mode='w+', prefix="peer_c", dir=const.PATH_DOWNLOAD, delete=False)
        return temp_file

    def __repr__(self):
        """
            Returns the file details
        """
        return f"_PeerFile(paths={self.file_paths.__repr__()})"

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


GROUP_MIN = 2
GROUP_MID = 4
GROUP_MAX = 6


class _FileGroup:
    def __init__(self, files: list[_FileItem] = None, *, bandwidth: int = 1024 * 1024 * 512, level: int):
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
            if file_size >= 1024 ** 3 or isclose(file_size, 1024 ** 3, rel_tol=0.0002):  # check again ??
                parts.append([file])
                current_part_size = 0
            else:
                parts.append([file])
                current_part_size = file_size


        self.grouped_files = parts
        self._re_group_if_needed()

    def _adjust_part_size(self) -> int:
        if self.grouping_level == GROUP_MIN:
            return self.total_size // 2
        elif self.grouping_level == GROUP_MAX:
            return self.total_size // 6
        return self.total_size // 4

    def _re_group_if_needed(self):
        max_parts = self.grouping_level

        if len(self.grouped_files) > max_parts:
            self.re_group(max_parts)

    def re_group(self, size: int):
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
        return len(self.grouped_files)

    def __iter__(self):
        return iter(self.grouped_files)

    def __str__(self):
        string = (f'total size: {_FileItem.stringify_size(self.total_size)}\t'
                  f'part size : {_FileItem.stringify_size(self.part_size)}\n')

        parts_str = "\n".join(
            f"{_FileItem.stringify_size(sum(file.size for file in part))} : {part}" for part in self.grouped_files)

        return string + parts_str


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

    def connect_sockets(self, sender_ip: Tuple[Any, ...]):
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

    def __len__(self):
        return self.sock_list.__len__()

    def __iter__(self):
        return self.sock_list.__iter__()


def make_file_items(paths: list[_FilePath]) -> list[_FileItem]:
    items = [_FileItem(os.path.basename(x), os.path.getsize(x), x) for x in paths]
    return items


def make_file_groups(file_list: list[_FilePath], grouping_level: int) -> _FileGroup:
    """

    A factory function which
    converts given list of file paths into a program required format of LIST[tuple(NAME, SIZE, FULL_PATH)]
    then passes it into _FileGroup()
    generates groups by calling func `_FileGroup::group`

    :param grouping_level: specifies grouping level
    :returns _FileGroup:
    :param file_list:
    """

    file_items = make_file_items(paths=file_list)
    grouped = _FileGroup(file_items, level=grouping_level)
    grouped.group()
    return grouped


def make_sock_groups(sock_count: int, *, connect_ip: tuple[Any, ...] = None,
                     bind_ip: tuple[Any, ...] = None) -> _SockGroup:
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


# deprecated file class


@NotInUse
class _PeerFile:
    __annotations__ = {
        'uri': Tuple[str, int],
        'path': str,
        '__control_flag': bool,
        'chunk_size': int,
        'error_ext': str
    }

    __dict__ = {'uri': ('localhost', 8080), 'path': '', '__control_flag': True, 'chunk_size': 1024 * 512,
                'error_ext': '.invalid'}

    __slots__ = ('__code__', '_lock', '__control_flag', '__chunk_size', '__error_extension', '__sock', 'uri', 'path',
                 'filename', 'file_size', 'type', 'raw_size')

    def __init__(self,
                 uri: Tuple[str, int],
                 path: str = '',
                 chunk_size: int = 1024 * 512,
                 error_ext: str = '.invalid'
                 ):

        self.__code__ = None
        self._lock = threading.Lock()
        self.__chunk_size = chunk_size
        self.__error_extension = error_ext
        self.__control_flag = True
        self.__sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
        self.uri = uri
        if path == '':
            return

        self.path = Path(path).resolve()

        if not self.path.exists():
            raise FileNotFoundError(f"File not found: {self.path}")

        if self.path.is_dir():
            raise NotADirectoryError(f"Cannot send a directory: {self.path}")

        if not self.path.is_file():
            raise IsADirectoryError(f"Not a regular file: {self.path}")

        self.filename = self.path.name
        self.file_size = self.path.stat().st_size
        self.type = self.path.suffix
        self.raw_size = struct.pack('!Q', self.file_size)

    def verify_handshake(self) -> Union[bool, None]:
        with self._lock:
            if not self.set_up_socket_connection():
                return False
            if not self.__control_flag:
                return False
            self.__sock.sendall(self.raw_size)

            return SimplePeerText(self.__sock, const.CMD_FILESOCKET_HANDSHAKE).send()

    def recv_handshake(self) -> bool:

        with self._lock:
            # try:

            self.__sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
            try:
                self.__sock.connect(self.uri)
            except socket.error as e:
                error_log(f"got error : {e} at fileobject :{self} from recv_handshake()/fileobject.py")

            self.file_size = struct.unpack('!Q', self.__sock.recv(8))[0]
            return SimplePeerText(self.__sock).receive(cmp_string=const.CMD_FILESOCKET_HANDSHAKE)
            # except Exception as e:
            #     print(f'::got {e} at avails\\fileobject.py from self.recv_handshake() closing connection')
            #     # error_log(f'::got {e} at core\\__init__.py from self.recv_handshake() closing connection')
            #     return False

    def send_file(self):
        """
           Sends the file contents to the receiver.
           Once this function is called the handshake is no longer valid cause this function closes the socket
           after file contents are transferred

           Returns:
               bool: True if the file was sent successfully, False otherwise.
        """
        with self._lock:
            # try:
            with self.__sock:
                send_progress = tqdm.tqdm(range(self.file_size), f"::sending {self.filename[:20]} ... ", unit="B",
                                          unit_scale=True, unit_divisor=1024)
                for data in self.__chunkify__():  # send the file in chunks
                    self.__sock.sendall(data)
                    send_progress.update(len(data))
                send_progress.close()
            return True
            # except Exception as e:
            #     error_log(f'::got {e} at core\\__init__.py from self.__send_file()/fileobject.py closing connection')
            #     return False
            # finally:
            #     self.__sock.close()

    def recv_file(self):
        """
        Receives the file contents from the sender.

        Returns:
            bool: True if the file was received successfully, False otherwise.
        """
        with self._lock:
            # try:
            # received_bytes = 0
            progress = tqdm.tqdm(range(self.file_size), f"::receiving {self.filename[:20]}... ", unit="B",
                                 unit_scale=True,
                                 unit_divisor=1024)
            with open(os.path.join(const.PATH_DOWNLOAD, self.__validatename__(self.filename)), 'wb') as file:
                while self.__control_flag and (data := self.__sock.recv(self.__chunk_size)):
                    file.write(data)
                    progress.update(len(data))
            progress.close()
            print()
            activity_log(f'::received file {self.filename} :: from {self.__sock.getpeername()}')
            return True
            # except Exception as e:
            #     error_log(f'::got {e} at avails\\fileobject.py from self.__recv_file()/fileobject.py closing connection')
            #     self.__sock.close()
            #     self.__file_error__()
            #     return False

    def __file_error__(self):
        """
            Handles file errors by renaming the file with an error extension.
        """
        with self._lock:
            os.rename(self.filename, self.filename + self.__error_extension)
            self.filename += self.__error_extension
        return True

    def __chunkify__(self):
        with open(self.path, 'rb') as file:
            while self.__control_flag and (chunk := file.read(self.__chunk_size)):
                yield chunk

    def get_meta_data(self) -> dict[str, str | int]:
        """Returns metadata as python dict, format name:'',size:'',type:''"""
        return {
            'name': self.filename,
            'size': self.file_size,
            'type': self.type
        }

    def set_up_socket_connection(self):
        self.__sock.settimeout(5)
        self.__sock.bind(self.uri)
        self.__sock.listen(1)
        # try:
        while True:
            readable, _, _ = select.select([self.__sock], [], [], 0.001)
            if self.__sock in readable:
                self.__sock, _ = self.__sock.accept()
                return True
        # except Exception as e:
        #     use.echo_print(False,
        #                    f'::got {e} at core\\__init__.py from self.set_up_socket_connection() closing connection')
        #     # error_log(f'::got {e} at core\\__init__.py from self.set_up_socket_connection() closing connection')
        #     return False

    def set_meta_data(self, *, filename, file_size=0, control_flag=threading.Event(), chunk_size: int = 1024 * 512,
                      error_ext: str = '.invalid'):
        self.filename = filename
        self.file_size = file_size
        self.__control_flag = control_flag
        self.__chunk_size = chunk_size
        self.__error_extension = error_ext

    def __validatename__(self, file_addr: str) -> str:
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
        self.filename = os.path.basename(new_file_name)
        return new_file_name

    def __len__(self):
        """
            Returns the file size.
        """
        return self.file_size

    def __str__(self):
        """
            Returns the file details
        """
        return (
            f"file name {self.filename}",
            f"file size {self.file_size}"
            f"sending to {self.__sock.getpeername()}"
            f"receiving from --"
        )

    def hold(self):
        self.__control_flag = not self.__control_flag

    def force_stop(self):
        self.__control_flag = not self.__control_flag
        try:
            self.__sock.close()
        except socket.error as e:
            error_log(f'::got {e} from self.force_stop()/fileobject.py closing connection')
        return True
