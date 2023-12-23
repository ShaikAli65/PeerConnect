from core import *


class PeerFile:
    """
        Encapsulates file operations for peer-to-peer file transfer.

        Allows sending and receiving files over sockets, managing file information,
        handling potential conflicts with existing files, and providing file-like
        behavior for iteration and size retrieval.
    """

    def __init__(self, path: str = '', sock: socket.socket = None, chucksize: int = 2048, error_ext: str = '.invalid'):
        self.sock = sock
        if path == '':
            return
        self.path = path
        self.file = open(path, 'rb')
        self.filename = os.path.basename(path)
        self.namelength = len(self.filename)
        self.filesize = os.path.getsize(path)
        self._lock = threading.Lock()
        self.chunksize = chucksize
        self.errorextension = error_ext

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
                    meta_data_filename = PeerText(self.filename, sock)
                    meta_data_filename.send()
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
                    self.filename = sock.recv(self.namelength).decode(const.FORMAT)
                    sock.sendall(struct.pack('!I', ))
                    sock.send(const.FILESENDINTITATEHEADER)
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
