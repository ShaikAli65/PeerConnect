import os
import socket
import time

from avails.remotepeer import RemotePeer
from core import *
from avails.textobject import PeerText


class PeerFile:
    """
        Encapsulates file operations for peer-to-peer file transfer.

        Allows sending and receiving files over sockets, managing file information,
        handling potential conflicts with existing files, and providing file-like
        behavior for iteration and size retrieval.

        Ths Class Does Provide Error Handling Not Need To Be Handled At Calling Functions.
    """

    def __init__(self, path: str = '', obj=None, recv_soc: socket.socket = None, chunksize: int = 2048,
                 error_ext: str = '.invalid'):
        self.remote_obj: RemotePeer = obj
        self._lock = threading.Lock()
        self.chunksize = chunksize
        self.errorextension = error_ext
        self.sock = None
        path = path.replace('\n', '')
        if path == '':
            self.sock = recv_soc
            self.path = path
            self.file = None
            self.filename = ''
            self.namelength = len(self.filename)
            self.filesize = 0
            return
        self.path = path
        self.file = open(path, 'rb')
        self.filename = os.path.basename(path)
        self.raw_size = struct.pack('!Q', os.path.getsize(path))

    def send_meta_data(self) -> bool:

        with self._lock:
            send_file_sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
            try:
                send_file_sock.connect(self.remote_obj.uri)
                PeerText(send_file_sock, const.CMD_RECV_FILE).send()
                time.sleep(0.15)
                PeerText(send_file_sock, self.filename).send()
                send_file_sock.sendall(self.raw_size)
                self.sock = send_file_sock
                return PeerText(send_file_sock, const.CMD_FILESOCKET_HANDSHAKE).send()
            except Exception as e:
                errorlog(f'::got {e} at core\\__init__.py from self.send_meta_data() closing connection')
                return False

    def recv_meta_data(self) -> bool:

        with self._lock:
            try:
                self.filename = PeerText(self.sock).receive()
                self.filesize = struct.unpack('!Q', self.sock.recv(8))[0]
                return PeerText(self.sock).receive(cmpstring=const.CMD_FILESOCKET_HANDSHAKE)
            except Exception as e:
                errorlog(f'::got {e} at core\\__init__.py from self.recv_meta_data() closing connection')
                return False

    def send_file(self):
        """
           Sends the file contents to the receiver.

           Returns:
               bool: True if the file was sent successfully, False otherwise.
        """
        with self._lock:
            try:
                while data := self.file.read(self.chunksize):
                    self.sock.sendall(data)
                activitylog(f'::sent file to {self.sock.getpeername()}')
                return True
            except Exception as e:
                errorlog(f'::got {e} at core\\__init__.py from self.send_file() closing connection')
                return False
            finally:
                self.file.close()

    def recv_file(self):
        """
            Receives the file contents from the sender.

            Returns:
                bool: True if the file was received successfully, False otherwise.
        """

        with self._lock:
            try:
                with open(os.path.join(const.DOWNLOADIR, self.__validatename(self.filename)), 'wb') as file:
                    while data := self.sock.recv(self.chunksize):
                        file.write(data)
                activitylog(f'::recieved file from {self.sock.getpeername()}')
                with open(self.filename, 'rb') as file:
                    self.file = file
                return True
            except Exception as e:
                errorlog(f'::got {e} at core\\__init__.py from self.recv_file() closing connection')
                self.__file_error()
                return False

    def __file_error(self):
        """
            Handles file errors by renaming the file with an error extension.
        """
        with self._lock:
            os.rename(self.filename, self.filename + self.errorextension)
            self.filename += self.errorextension
        return True

    def __validatename(self, fileaddr: str):
        """
            Ensures a unique filename if a file with the same name already exists.

            Args:
                fileaddr (str): The original filename.

            Returns:
                str: The validated filename, ensuring uniqueness.
        """
        base, ext = os.path.splitext(fileaddr)
        counter = 1
        new_file_name = fileaddr
        while os.path.exists(os.path.join(const.DOWNLOADIR, new_file_name)):
            new_file_name = f"{base}({counter}){ext}"
            counter += 1
        self.filename = os.path.basename(new_file_name)
        self.namelength = len(self.filename)
        return new_file_name

    def __iter__(self):
        """
            Returns an iterator over the file's contents.
        """
        return self.file

    def __next__(self):
        """
           Returns the next chunk of data from the file.
       """
        return next(self.file)

    def __len__(self):
        """
            Returns the file size.
        """
        return self.filesize

    def __str__(self):
        """
            Returns the filename.
        """
        return self.filename


"""
import ftplib

class PeerFile:
    ...  # Existing class code

    def send_file_ftp(self):

        with self._lock:
            try:
                with ftplib.FTP(const.FTP_SERVER, const.FTP_USER, const.FTP_PASSWORD) as ftp:
                    ftp.storbinary(f"STOR {self.filename}", self.file)
                    activitylog(f'::sent file to {const.FTP_SERVER}')
                    return True
            except Exception as e:
                errorlog(f'::got {e} at core\\__init__.py from self.send_file_ftp() closing connection')
                return False

    def recv_file_ftp(self):

        with self._lock:
            try:
                with ftplib.FTP(const.FTP_SERVER, const.FTP_USER, const.FTP_PASSWORD) as ftp:
                    with open(os.path.join(const.DOWNLOADIR, self.filename), 'wb') as file:
                        ftp.retrbinary(f"RETR {self.filename}", file.write)
                    activitylog(f'::received file from {const.FTP_SERVER}')
                    self.file = file
                    return True
            except Exception as e:
                errorlog(f'::got {e} at core\\__init__.py from self.recv_file_ftp() closing connection')
                self.__file_error()
                return False
"""
