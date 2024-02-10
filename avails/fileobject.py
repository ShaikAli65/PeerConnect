import os
import sys

from core import *
from avails.textobject import PeerText


class PeerFile:

    def __init__(self, path: str = '', obj=None, recv_soc: socket.socket = None, chunk_size: int = 2048,
                 error_ext: str = '.invalid'):
        self.reciever_obj: RemotePeer = obj
        self._lock = threading.Lock()
        self.chunk_size = chunk_size
        self.error_extension = error_ext
        self.sock = None
        path = path.replace('\n', '').replace('\"','').strip()
        if path == '':
            self.sock = recv_soc
            self.path = ''
            self.filename = ''
            self.name_length = len(self.filename)
            self.file_size = 0
            return
        self.path = path
        self.filename = os.path.basename(path)
        self.raw_size = struct.pack('!Q', os.path.getsize(path))

    def send_meta_data(self) -> bool:

        with self._lock:
            self.sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
            try:
                self.sock.connect(self.reciever_obj.uri)
                PeerText(self.sock, const.CMD_RECV_FILE,byteable=False).send()
                PeerText(self.sock, self.filename).send()
                self.sock.sendall(self.raw_size)
                return PeerText(self.sock, const.CMD_FILESOCKET_HANDSHAKE).send()
            except Exception as e:
                print(f'::got {e} at core\\__init__.py from self.send_meta_data() closing connection')
                # error_log(f'::got {e} at core\\__init__.py from self.send_meta_data() closing connection')
                return False

    def recv_meta_data(self) -> bool:

        with self._lock:
            try:
                self.filename = PeerText(self.sock).receive().decode(const.FORMAT)
                self.file_size = struct.unpack('!Q', self.sock.recv(8))[0]

                return PeerText(self.sock).receive(cmpstring=const.CMD_FILESOCKET_HANDSHAKE)
            except Exception as e:
                print(f'::got {e} at avails\\fileobject.py from self.recv_meta_data() closing connection')
                # error_log(f'::got {e} at core\\__init__.py from self.recv_meta_data() closing connection')
                return False

    def send_file(self):
        """
           Sends the file contents to the receiver.

           Returns:
               bool: True if the file was sent successfully, False otherwise.
        """
        with self._lock:
            try:
                self.chunk_size = 2048*4
                with open(self.path, 'rb') as file:
                    while data := file.read(self.chunk_size):
                        self.sock.sendall(data)
                # activity_log(f'::sent file to {self.sock.getpeername()}')
                print("::file sent: ", self.filename, " to ", self.sock.getpeername())
                return True
            except Exception as e:
                error_log(f'::got {e} at core\\__init__.py from self.send_file() closing connection')
                return False
            finally:
                self.sock.close()

    def recv_file(self):
        """
        Receives the file contents from the sender.

        Returns:
            bool: True if the file was received successfully, False otherwise.
        """
        with self._lock:
            try:
                print(f"::receiving file {self.filename}")
                received_bytes = 0
                with open(os.path.join(const.DOWNLOAD_PATH, self.__validatename(self.filename)), 'wb') as file:
                    while data := self.sock.recv(self.chunk_size):
                        file.write(data)
                        received_bytes += len(data)
                        progress_percentage = (received_bytes / self.file_size) * 100
                        print(f"\r::file received: {progress_percentage:.2f}%", end="")
                        sys.stdout.flush()
                print()
                activity_log(f'::received file {self.filename} :: from {self.sock.getpeername()}')
                return True
            except Exception as e:
                error_log(f'::got {e} at avails\\fileobject.py from self.recv_file() closing connection')
                self.sock.close()
                self.__file_error()
                return False

    def __file_error(self):
        """
            Handles file errors by renaming the file with an error extension.
        """
        with self._lock:
            os.rename(self.filename, self.filename + self.error_extension)
            self.filename += self.error_extension
        return True

    def __validatename(self, file_addr: str):
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
        while os.path.exists(os.path.join(const.DOWNLOAD_PATH, new_file_name)):
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
        return self.filename

