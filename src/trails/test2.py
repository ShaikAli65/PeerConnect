import tqdm
from pathlib import Path
from src.core import *
from src.avails.textobject import SimplePeerText


class PeerFile:

    def __init__(self,
                 paths: list[Path | str] = "", *,
                 download_path: str = const.PATH_DOWNLOAD,
                 control_flag=True,
                 chunk_size: int = 1024 * 512,
                 error_ext: str = '.invalid'
                 ):

        self.__control_flag = control_flag
        self.__chunk_size = chunk_size
        self.__error_extension = error_ext
        self.download_path = os.path.abspath(download_path)
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
            self.file_paths.append((os.path.basename(file_path), os.path.getsize(file_path), os.path.abspath(file_path)))

    def __send_file(self, receiver_sock: socket.socket, *, file_paths_index: int):
        """
           Consumes first file in the list,
           Sends the file contents to the receiver.

           Returns:
               bool: True if the file is sent successfully, False otherwise.
        """

        filename, file_size, file_path = self.file_paths[file_paths_index]

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

        return SimplePeerText(receiver_sock, text=const.CMD_FILESOCKET_HANDSHAKE, byte_able=True).send()

    def __recv_file(self, sender_sock: socket.socket):

        """
        Receives the file contents from the sender.
        and saves them with received data to Downloads/PeerConnect
        adds that file path to the self. paths attribute of the class
        Returns:
            bool: True if the file was received successfully, False otherwise.
        """

        filename = SimplePeerText(sender_sock).receive().decode(const.FORMAT)
        file_path = os.path.join(self.download_path, self.__validatename__(filename))
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
                data = sender_sock.recv(min(self.__chunk_size, file_size))
                file.write(data)
                progress.update(len(data))
                file_size -= len(data)
        progress.close()
        print()
        return SimplePeerText(refer_sock=sender_sock).receive(const.CMD_FILESOCKET_HANDSHAKE)

    def send_files(self, receiver_sock: socket.socket):
        """
        Sends all files in the list to the receiver.

        Returns:
            bool: True if all files are sent successfully, False otherwise.
        """
        raw_file_count = struct.pack('!I', len(self.file_paths))
        receiver_sock.send(raw_file_count)

        for i in range(len(self.file_paths)):
            if not self.__send_file(receiver_sock, file_paths_index=i):
                return False
        return True

    def recv_files(self, sender_sock: socket.socket):
        """
        Receives all files from the sender.

        Returns:
            bool: True if all files are received successfully, False otherwise.
        """
        raw_file_count = sender_sock.recv(4)
        file_count = struct.unpack('!I', raw_file_count)[0]

        for _ in range(file_count):
            if not self.__recv_file(sender_sock):
                return False
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

    def __str__(self):
        """
            Returns the file details
        """
        return ""

    def break_loop(self):
        self.__control_flag = not self.__control_flag

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


if __name__ == "__main__":
    file1 = PeerFile(download_path="")
    soc = socket.socket(socket.AF_INET6,socket.SOCK_STREAM)
    soc.connect(("2001:4490:4c61:f5:210f:719e:6e68:bed6", 8000))

    print("connected to server :")
    file1.recv_files(soc)
    print("files received.")
    soc.close()
