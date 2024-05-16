import os.path
import tqdm
from pathlib import Path
import tempfile

from src.core import *
from src.avails.textobject import SimplePeerText  # , DataWeaver
from src.managers import filemanager  # , error_manager


class _PeerFile:

    def __init__(self,
                 paths: list[Path | str] = "", *,
                 chunk_size: int = 1024 * 512,
                 error_ext: str = '.invalid'
                 ):

        self.__control_flag = True
        self.__chunk_size = chunk_size
        self.__error_extension = error_ext
        self.file_paths = []
        if not paths:
            return

        for file_path in paths:

            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            if os.path.isdir(file_path):
                raise NotADirectoryError(f"Cannot use a directory in PeerFile: {file_path}")

            if not os.path.isfile(file_path):
                raise IsADirectoryError(f"Not a regular file: {file_path}")
            self.file_paths.append(
                (os.path.basename(file_path), os.path.getsize(file_path), os.path.abspath(file_path)))

    def __send_file(self, receiver_sock: socket.socket, *, file: Tuple[str, int, str]):
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

        send_progress = tqdm.tqdm(range(file_size), f"::sending {filename[:20]} ... ", unit="B", unit_scale=True,
                                  unit_divisor=1024)
        for data in self.__chunkify__(file_path):  # send the file in chunks
            receiver_sock.sendall(data)
            send_progress.update(len(data))
        send_progress.close()

        return SimplePeerText(receiver_sock, text=const.CMD_FILESUCCESS, byte_able=False).send()

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
        file_raw_size = sender_sock.recv(8)
        if not len(file_raw_size) == 8:
            raise ValueError(f"Received file size buffer is not 8 bytes {file_raw_size}")

        file_size: int = struct.unpack('!Q', file_raw_size)[0]
        self.calculate_chunk_size(file_size)
        progress = tqdm.tqdm(range(file_size), f"::receiving {filename[:20]}... ", unit="B", unit_scale=True,
                             unit_divisor=1024)
        self.file_paths.append((filename, file_size, file_path))

        with open(file_path, 'wb') as file:
            while self.__control_flag and file_size > 0:
                # try:
                data = sender_sock.recv(min(self.__chunk_size, file_size))
                # error_manager.ErrorManager(error=err,......
                #       connectionspass
                file.write(data)
                progress.update(len(data))
                file_size -= len(data)

        progress.close()
        print()
        return SimplePeerText(refer_sock=sender_sock).receive(const.CMD_FILESUCCESS)

    def send_files(self, receiver_sock: socket.socket):
        """
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

    def __chunkify__(self, file_path):
        with open(file_path, 'rb') as file:
            while self.__control_flag and (chunk := file.read(self.__chunk_size)):
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

    def break_loop(self):
        self.__control_flag = False

    def calculate_chunk_size(self, file_size):
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
    def __init__(self,*, files: List[str | Path] = None, bandwidth: int = 1024*1024*512, latency: int):

        self.files = files
        self.grouped_files = [(self.files,), ]
        self.bandwidth, self.latency = bandwidth, latency

    def group(self):
        """

        bandwidth :highest speed x MB/s
        latency : 2ms
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

        self.files.sort(key=lambda x: os.path.getsize(x))

        file_groups = []
        current_group = []
        total_group_size = 0

        for file in self.files:
            file_size = os.path.getsize(file)

            # Consider estimated speed and bandwidth for group size
            if (total_group_size + file_size) <= self.bandwidth - self.latency:
                current_group.append(file)
                total_group_size += file_size
            else:
                file_groups.append(tuple(current_group))
                current_group = [file]
                total_group_size = file_size

        if current_group:
            file_groups.append(tuple(current_group))

            return self.grouped_files

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
    def __init__(self, sock_count: int):
        self.sock_list = []
        self.sock_count = sock_count
        self.control_flag = True

    def get_sockets_from(self, connection_sock: socket.socket):
        for i in range(self.sock_count):

            while self.control_flag:
                readable, _, _ = select.select([connection_sock, ], [], [], 0.001)
                if connection_sock in readable:
                    break

            conn, _ = connection_sock.accept()

            if SimplePeerText(refer_sock=conn, text=const.SOCKET_OK, byte_able=False).send():
                self.sock_list.append(conn)

    def connect_sockets(self, sender_ip: Tuple[str, int]):
        for i in range(self.sock_count):
            _sock = socket.socket(const.IP_VERSION, const.PROTOCOL)

            while self.control_flag:
                readable, _, _ = select.select([_sock, ], [], [], 0.001)
                if _sock in readable:
                    break

            _sock.connect(sender_ip)
            if SimplePeerText(refer_sock=_sock).receive(cmp_string=const.SOCKET_OK):
                self.sock_list.append(_sock)

    def close(self):
        for sock in self.sock_list:
            try:
                sock.close()
            finally:
                sock.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __len__(self):
        return self.sock_list.__len__()

    def __iter__(self):
        return self.sock_list.__iter__()


if __name__ == "__main__":
    pass
