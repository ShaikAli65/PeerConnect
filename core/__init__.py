import threading
from collections.abc import MutableSet
import time
import socket
import os
import struct
import pickle

from logs import *


class Fluxuant(MutableSet):
    def __init__(self):
        self._data = set()
        self._changes = set()  # Track changes since the last synchronization
        self._lock = threading.Lock()

    def add(self, item):
        with self._lock:
            self._data.add(item)
            self._changes.add(('1', item))

    def discard(self, item):
        with self._lock:
            self._data.discard(item)
            self._changes.add(('0', item))

    def get_changes(self):
        with self._lock:
            changes = list(self._changes)
            self._changes.clear()  # Clear the changes after synchronization
            return changes

    def __contains__(self, item):
        with self._lock:
            return item in self._data

    def __iter__(self):
        with self._lock:
            return iter(self._data)

    def __len__(self):
        with self._lock:
            return len(self._data)

    def __str__(self) -> str:
        return super().__str__()


class NotInUse(DeprecationWarning):
    """A class to denote deprecated/not currently used functions/methods/classes"""

    def __init__(self, *args, **kwargs):
        pass


class PeerFILE:
    """
        Encapsulates file operations for peer-to-peer file transfer.

        Allows sending and receiving files over sockets, managing file information,
        handling potential conflicts with existing files, and providing file-like
        behavior for iteration and size retrieval.
    """

    def __init__(self, path: str = '', sock: socket.socket = None):
        self.sock = sock
        if path == '':
            return
        self.path = path
        self.file = open(path, 'rb')
        self.filename = os.path.basename(path)
        self.namelength = len(self.filename)
        self.filesize = os.path.getsize(path)
        self._lock = threading.Lock()
        self.chunksize = 2048

    def send_meta_data(self) -> bool:
        """
       Sends file metadata (size and name) to the receiver.

       Returns:
           bool: True if metadata was sent successfully, False otherwise.
       """
        with self.sock as sock:
            with self._lock:
                try:
                    sock.send(struct.pack('!Q', self.filesize))
                    sock.send(struct.pack('!I', self.namelength))
                    sock.send(self.filename.encode('utf-8'))
                    if sock.recv(1024).decode('utf-8') == 'ready':
                        return True
                    else:
                        return False
                except Exception as e:
                    errorlog(f'::got {e} at core\\__init__.py from self.send_meta_data() closing connection')
                    sock.close()
                    return False

    def recv_meta_data(self):
        """
            Receives file metadata (size and name) from the sender.

            Returns:
                bool: True if metadata was received successfully, False otherwise.
        """
        with self.sock as sock:
            with self._lock:
                try:
                    self.filesize = struct.unpack('!Q', sock.recv(8))[0]
                    self.namelength = struct.unpack('!I', sock.recv(4))[0]
                    self.filename = sock.recv(self.namelength).decode('utf-8')
                    sock.send('ready'.encode('utf-8'))
                    return True
                except Exception as e:
                    errorlog(f'::got {e} at core\\__init__.py from self.recv_meta_data() closing connection')
                    sock.close()
                    return False

    def send_file(self):
        """
           Sends the file contents to the receiver.

           Returns:
               bool: True if the file was sent successfully, False otherwise.
        """
        with self.sock as sock:
            with self._lock:
                try:
                    while data := self.file.read(self.chunksize):
                        sock.sendall(data)
                    self.file.close()
                    activitylog(f'::sent file to {sock.getpeername()}')
                    return True
                except Exception as e:
                    errorlog(f'::got {e} at core\\__init__.py from self.send_file() closing connection')
                    sock.close()
                    return False

    def recv_file(self):
        """
            Receives the file contents from the sender.

            Returns:
                bool: True if the file was received successfully, False otherwise.
        """
        with self.sock as sock:
            with self._lock:
                try:
                    with open(self.__validatename(self.filename), 'wb') as file:
                        while data := sock.recv(self.chunksize):
                            file.write(data)
                    activitylog(f'::recieved file from {sock.getpeername()}')
                    with open(self.filename, 'rb') as file:
                        self.file = file
                    return True
                except Exception as e:
                    errorlog(f'::got {e} at core\\__init__.py from self.recv_file() closing connection')
                    sock.close()
                    return False

    def __validatename(self, file_path: str):
        """
            Ensures a unique filename if a file with the same name already exists.

            Args:
                file_path (str): The original filename.

            Returns:
                str: The validated filename, ensuring uniqueness.
        """
        base, ext = os.path.splitext(file_path)
        counter = 1
        new_file_path = file_path
        while os.path.exists(new_file_path):
            new_file_path = f"{base}({counter}){ext}"
            counter += 1
        self.filename = os.path.basename(new_file_path)
        return new_file_path

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
