import asyncio
import contextlib
import mmap
import socket
import struct
from contextlib import aclosing
from pathlib import Path

from src.avails import Wire, WireData, connect, const
from src.avails.status import StatusMixIn
from src.core import get_this_remote_peer
from src.transfers import HEADERS, TransferState
from src.transfers.files._fileobject import FileItem, calculate_chunk_size
from src.transfers.files._logger import logger as _logger


class Sender(StatusMixIn):
    version = const.VERSIONS['FO']
    """
        stopping_flag(Callable[[],bool]): this gets called to check whether to stop or not, while sending chunks

        yield_freq(int): number of times this function should yield while sending chunks

    """

    def __init__(self, file_list, peer_obj, transfer_id, *, status_yield_frequency=10):
        self.state = TransferState.PREPARING
        self.file_list = [
            FileItem(x, seeked=0) for x in file_list
        ]
        self.socket = None
        self._file_id = transfer_id
        self.peer_obj = peer_obj
        super().__init__(status_yield_frequency)
        self.to_stop = False
        self._current_index = 0
        self._log_prefix = f"FILE[{self._file_id}]"
        self.send_func = None
        self.recv_func = None

    async def send_files(self):
        _logger.debug(f'{self._log_prefix} changing state to sending')
        self.state = TransferState.SENDING

        for index in range(self._current_index, len(self.file_list)):
            # there is another file incoming
            if self.to_stop:
                break
            file_item = self.file_list[index]
            self.current_file = index

            try:
                # a signal that says there is more to receive
                await self.send_func(struct.pack('?', True))
                await self._send_file_item(file_item)
                self.status_setup(
                    prefix=f"sending: {file_item}",
                    initial_limit=file_item.seeked,
                    final_limit=file_item.size
                )
                async with aclosing(self._send_single_file(file_item)) as sender:
                    async for items in sender:
                        yield items
            except OSError:
                _logger.error(f"{self._log_prefix} got os error, pausing transfer", exc_info=True)
                self.state = TransferState.PAUSED
                raise

        # end of transfer, signalling that there are no more files
        await self.send_func(struct.pack('?', False))
        _logger.info(f"{self._log_prefix} sent final flag, completed sending")
        self.state = TransferState.COMPLETED

    async def _send_file_item(self, file_item):
        file_object = bytes(file_item)
        file_packet = struct.pack('!I', len(file_object)) + file_object
        await self.send_func(file_packet)

    async def _send_single_file(self, file_item):
        async with aclosing(
                send_actual_file(
                    self.send_func,
                    file_item,
                )
        ) as send_file:
            async for seeked in send_file:
                self.update_status(seeked)
                if self.to_stop:
                    break
                if self.should_yield():
                    yield file_item, seeked

        print("file sent", file_item)

    @contextlib.asynccontextmanager
    async def prepare_connection(self):
        _logger.debug(f"{self._log_prefix} changing state to connection")  # debug
        self.state = TransferState.CONNECTING
        try:
            with await connect.connect_to_peer(
                    self.peer_obj,
                    connect.CONN_URI,
                    timeout=2,
                    retries=2,
            ) as connection:
                connection.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 1)
                await self._authorize_connection(connection)
                self.socket = connection
                self.send_func = connect.Sender(self.socket)
                self.recv_func = connect.Receiver(self.socket)

                _logger.debug(f"{self._log_prefix} connection established")
                yield
        except OSError as oops:
            if not self.state == TransferState.PAUSED:
                _logger.warning(f"{self._log_prefix} reverting state to PREPARING, failed to connect to peer",
                                exc_info=oops)
                self.state = TransferState.PREPARING
            raise

    async def _authorize_connection(self, connection):
        handshake = WireData(
            header=HEADERS.CMD_FILE_CONN,
            msg_id=get_this_remote_peer().peer_id,
            version=self.version,
            file_id=self._file_id,
        )
        await Wire.send_async(connection, bytes(handshake))
        _logger.debug("authorization header sent for file connection", extra={'id': self._file_id})

    async def continue_file_transfer(self):
        _logger.debug(f'FILE[{self._file_id}] changing state to sending')
        self.state = TransferState.SENDING
        start_file = self.file_list[self.current_file]
        self.to_stop = False

        # synchronizing last file sent
        seeked_int = await self.socket.recv(8)
        if not seeked_int:
            _logger.debug(f'FILE[{self._file_id}] changing state to paused')
            self.state = TransferState.PAUSED
            raise ConnectionResetError("Connection reset by other end while received file seek point")

        start_file.seeked = struct.unpack('!Q', seeked_int)[0]
        self.status_setup(f"resuming file:{start_file}", start_file.seeked, start_file.size)
        async with aclosing(self._send_single_file(start_file)) as initial_file_sender:
            async for items in initial_file_sender:
                yield items
        # end of broken file transfer

        # continuing with remaining transfer
        async with aclosing(self.send_files()) as file_sender:
            async for items in file_sender:
                yield items

    def attach_files(self, paths_list):
        self.file_list.extend(FileItem(Path(path), 0) for path in paths_list)

    @property
    def id(self):
        return self._file_id


async def send_actual_file(
        send_function,
        file,
        *,
        chunk_len=None,
        timeout=5
):
    """Sends file to other end using ``send_function``

    Opens file in **rb** mode from the ``path`` attribute from ``file item``
    reads ``seeked`` attribute of ``file item`` to start the transfer from
    calls ``send_function`` and awaits on it every time this function tries to send a chunk
    if chunk_size parameter is not provided then calculates chunk size by calling ``calculate_chunk_size``

    Args:
        send_function(Callable): function to call when a chunk is ready
        file(FileItem): file to send
        chunk_len(int): length of each chunk passed into ``send_function`` for each call
        timeout(int): timeout in seconds used to wait upon send_function

    Yields:
        number indicating the sent file size
    """

    chunk_size = chunk_len or calculate_chunk_size(file.size)

    with open(file.path, 'rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as f_mapped:
            seek = file.seeked
            for offset in range(seek, file.size, chunk_size):
                chunk = f_mapped[offset: offset + chunk_size]
                await asyncio.wait_for(send_function(chunk), timeout)
                seek += len(chunk)
                file.seeked = seek
                yield seek
