import socket

import tqdm
from pathlib import Path

from src.core import *
from src.avails.textobject import SimplePeerText
from src.avails import useables as use


class PeerFile:
    def __init__(self,
                 uri: tuple[str, int],
                 path: str = '',
                 control_flag=threading.Event(), chunk_size: int = 1024 * 512, error_ext: str = '.invalid'):

        self._lock = threading.Lock()
        self.__control_flag: threading.Event = control_flag
        self.__chunk_size = chunk_size
        self.__error_extension = error_ext
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
            if self.__control_flag.is_set():
                return False
            self.__sock.sendall(self.raw_size)
            return SimplePeerText(self.__sock, const.CMD_FILESOCKET_HANDSHAKE).send()

    def recv_handshake(self) -> bool:

        with self._lock:
            # try:

            self.__sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
            self.__sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.__chunk_size)
            try:
                self.__sock.connect(self.uri)
            except socket.error as e:
                error_log(f"got error : {e} at fileobject :{self} from recv_meta_data(self)/fileobject.py")

            self.file_size = struct.unpack('!Q', self.__sock.recv(8))[0]
            return SimplePeerText(self.__sock).receive(cmp_string=const.CMD_FILESOCKET_HANDSHAKE)
            # except Exception as e:
            #     print(f'::got {e} at avails\\fileobject.py from self.recv_handshake() closing connection')
            #     # error_log(f'::got {e} at core\\__init__.py from self.recv_handshake() closing connection')
            #     return False

    def send_file(self):
        """
           Sends the file contents to the receiver.

           Returns:
               bool: True if the file was sent successfully, False otherwise.
        """
        with self._lock:
            # try:
            send_progress = tqdm.tqdm(range(self.file_size), f"::sending {self.filename[:20]} ... ", unit="B",
                                      unit_scale=True, unit_divisor=1024)
            for data in self.__chunkify__():  # send the file in chunks
                self.__sock.sendall(data)
                send_progress.update(len(data))
            send_progress.close()
            return True
            # except Exception as e:
            #     error_log(f'::got {e} at core\\__init__.py from self.send_file() closing connection')
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
                while (not self.__control_flag.is_set()) and (data := self.__sock.recv(self.__chunk_size)):
                    file.write(data)
                    progress.update(len(data))
            progress.close()
            print()
            activity_log(f'::received file {self.filename} :: from {self.__sock.getpeername()}')
            return True
            # except Exception as e:
            #     error_log(f'::got {e} at avails\\fileobject.py from self.recv_file() closing connection')
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
            while (not self.__control_flag.is_set()) and (chunk := file.read(self.__chunk_size)):
                yield chunk

    def get_meta_data(self) -> str:
        """Returns metadata as json string in format name:'',size:'',type:''"""
        return json.dumps({
            'name': self.filename,
            'size': self.file_size,
            'type': self.type
        })

    def set_up_socket_connection(self):
        self.__sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.__chunk_size)
        self.__sock.settimeout(5)
        self.__sock.bind(self.uri)
        self.__sock.listen(1)
        # try:
        while True:
            read_ables, _, _ = select.select([self.__sock], [], [], 0.001)
            if self.__sock in read_ables:
                self.__sock, _ = self.__sock.accept()
                return True
        # except Exception as e:
        #     use.echo_print(False,
        #                    f'::got {e} at core\\__init__.py from self.set_up_socket_connection() closing connection')
        #     # error_log(f'::got {e} at core\\__init__.py from self.set_up_socket_connection() closing connection')
        #     return False

    def set_meta_data(self, filename, file_size=0, control_flag=threading.Event(), chunk_size: int = 1024 * 512,
                      error_ext: str = '.invalid'):
        self.filename = filename
        self.file_size = file_size
        self.__control_flag = control_flag
        self.__chunk_size = chunk_size
        self.__error_extension = error_ext

    def __validatename__(self, file_addr: str):
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
        self.name_length = len(self.filename)
        return new_file_name

    def __len__(self):
        """
            Returns the file size.
        """
        return self.file_size

    def __str__(self):
        """
            Returns the filename.
        """
        return (
            f"file name {self.filename}",
            f"file size {self.file_size}"
            f"sending to {self.__sock.getpeername()}"
            f"receiving from --"
        )

    def hold(self):
        self.__control_flag.set()

    def force_stop(self):
        self.__control_flag.set()
        try:
            self.__sock.close()
        except socket.error as e:
            error_log(f'::got {e} at fileobject.py\\avails.py from self.force_stop() closing connection')
        return True


# ++++++++++++++++--------------------------------------------------------------------------------------------------++++++++++++++++


def calculate_buffer_size(file_size):
    # Define the minimum and maximum buffer sizes
    min_buffer_size = 64 * 1024  # 64 KB
    max_buffer_size = 1024 * 1024  # 1 MB

    # Define the minimum and maximum file sizes
    min_file_size = 0  # Smallest file size
    max_file_size = 1024 * 1024 * 1024  # 1 GB (adjust as needed)

    # Calculate the buffer size based on the file size
    if file_size <= min_file_size:
        return min_buffer_size
    elif file_size >= max_file_size:
        return max_buffer_size
    else:
        # Linear scaling between min and max buffer sizes
        buffer_size = min_buffer_size + (max_buffer_size - min_buffer_size) * (file_size - min_file_size) / (
                max_file_size - min_file_size)
        return int(buffer_size)
