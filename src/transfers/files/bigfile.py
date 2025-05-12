import asyncio
import struct
from asyncio import TaskGroup
from contextlib import aclosing
from functools import wraps
from itertools import count

from src import net
from src.avails import const
from src.avails.exceptions import CancelTransfer, InvalidStateError, TransferIncomplete
from src.transfers import HEADERS, TransferState, _logger
from src.transfers.abc import AbstractReceiver, AbstractSender
from src.transfers.status import StatusIterator
from ._fileobject import FileItem
from ._merge import merge_all_and_delete
from .receiver import Receiver as FReceiver
from .sender import Sender as FSender

CHUNK_SIZE = 30 * 1024 * 1024  # 30MB


async def bomb():
    raise (
        "cancel all tasks in taskgroup"
    )  # change this to an exception with specificity


class _ControlMixIn:
    async def pause(self):
        for i, connection in self.connections.items():
            connection.send.pause()
            connection.recv.pause()

        _logger.debug(f"{self._log_prefix} pausing the transfer")
        self.state = TransferState.PAUSED

    async def resume(self):
        for i, connection in self.connections.items():
            connection.send.resume()
            connection.recv.resume()

        _logger.debug(f"{self._log_prefix} resuming the transfer")
        self.state = TransferState.RECEIVING


class _CancelMixIn:
    async def cancel(self):
        if self.state == TransferState.CONNECTING:
            if self._wait_for_first_connection.done():
                if self._wait_for_first_connection.exception():
                    return  # this is not an expected situation
            self.should_stop = True
            # TODO: what to do with connection ??
            self.state = TransferState.ABORTING
            return

        possible_states = (TransferState.SENDING, TransferState.RECEIVING, TransferState.PAUSED)
        if self.state not in possible_states:
            raise InvalidStateError(f"not expected transfer state in {self.state}")

        self.should_stop = True
        self.state = TransferState.ABORTING
        ct = CancelTransfer("User canceled the transfer")
        self.task_group.cancel_all_tasks(ct)

        await self.status_updater.stop(ct)  # this raises CancelTransfer in the start_transfer method


class _BigFileTaskGroup:
    def __init__(self):
        self.task_group = TaskGroup()

    def __aenter__(self):
        return self.task_group.__aenter__()

    def __aexit__(self, *args):
        return self.task_group.__aexit__(*args)

    @wraps(TaskGroup.create_task)
    def create_task(self, *args, **kwargs):
        return self.task_group.create_task(*args, **kwargs)

    @property
    def is_stopping(self):
        return getattr(self.task_group, '_exiting')

    def cancel_all_tasks(self, *args):
        for task in getattr(self.task_group, '_tasks'):
            if not task.done():
                task.cancel(*args)

    async def close(self):
        try:
            return await self.__aexit__(*[None] * 3)
        except* Exception as exps:
            # extract the exception related to big file transfer
            _raise = next(filter(
                lambda x: isinstance(x, TransferIncomplete | CancelTransfer),
                (arg for exp in exps.exceptions for arg in exp.args)
            ), None)

            if not _raise:
                raise  # reraise if no related exceptions found

        if _raise:
            raise _raise

    def refresh(self):
        self.task_group = TaskGroup()


class _BigChunkSender(FSender):
    def __init__(self, peer_obj, transfer_id, status_updater):
        super().__init__(
            peer_obj,
            transfer_id,
            [],
            status_updater,
        )

    async def send_big_chunk(self, big_chunk: FileItem, chunk_id):
        self._expected_exps.clear()
        self.files_to_send.clear()
        self.files_to_send.append(big_chunk)
        self.state = TransferState.SENDING
        await self.wrap_exp_handling(self.net_sender, struct.pack('!I', chunk_id))
        async with aclosing(self.start_transfer()) as loop:
            async for _ in loop:
                pass


class Sender(
    _CancelMixIn,
    _ControlMixIn,
    AbstractSender,
):
    """Send large file to a peer

    Big files often hit the slow speeds barrier due to TCP flow control. BigfileSender designed to
    operate with multiple connections to transfer a large file by making it into chunks.

    * `connection_made` method can be called to add multiple connections.
    * as soon as a connection is added, It starts a new part-sender that sends parts of bigfile to the other side
    see bigfile.Receiver for receiving logic

    This leads to efficient utilization of bandwidth, adding more connections pushes the network limit.

    """
    version = const.VERSIONS["FO"]

    def __init__(
          self, file_item, peer_obj, transfer_id, status_iterator: StatusIterator
    ):
        self.file = file_item
        self.peer_obj = peer_obj
        self.transfer_id = transfer_id
        self.status_updater: StatusIterator = status_iterator
        self.connections = {}
        self.connection_index_gen = count()
        self.state = TransferState.PREPARING
        self._sent_parts = {}
        self.failed_chunks = []
        self.file_iterator = self._bigfile_chunk_generator()
        self.should_stop = False
        self.task_group = _BigFileTaskGroup()
        self._wait_for_first_connection: asyncio.Future[net.Connection] = asyncio.get_running_loop().create_future()
        self._start_transfer = asyncio.Event()  # event to signal the start of transfer

    def _bigfile_chunk_generator(self):
        size = self.file.size
        start = 0
        for id, i in enumerate(range(start, size, CHUNK_SIZE)):
            if len(self.failed_chunks):
                yield self.failed_chunks.pop(0)
            yield id, i, i + CHUNK_SIZE

    async def __aenter__(self):
        self.state = TransferState.CONNECTING
        self.status_updater.status_setup(
            f"{self._log_prefix} sending file: {self.file}", self.file.seeked, self.file.size
        )
        await self.task_group.__aenter__()
        return self

    async def start_transfer(self):
        conn = await self._wait_for_first_connection
        await conn.send(struct.pack('!I', self.max_noof_parts))
        handshake = await conn.recv(1)
        assert handshake == HEADERS.CONTINUE_TRANSFER, "WTF"
        _logger.debug(f"{self._log_prefix} transfer handshake successful starting transfer")
        self.state = TransferState.SENDING
        self._start_transfer.set()
        async for update in self.status_updater:
            yield update

    def connection_made(self, connection):
        if not self._wait_for_first_connection.done():
            self._wait_for_first_connection.set_result(connection)

        _logger.debug(f"{self._log_prefix} adding new connection to send big chunks, {connection=}")

        idx = next(self.connection_index_gen)
        self.connections[idx] = connection
        self.task_group.create_task(self._send_task(connection, idx))

    async def _send_task(self, net_connection, index):
        await self._start_transfer.wait()
        if not self.state == TransferState.RECEIVING:
            return

        sender = _BigChunkSender(self.peer_obj, self.id, self.status_updater)
        sender.connection_made(net_connection)
        _logger.debug(f"{self._log_prefix} starting part sender with {index=}")

        for big_chunk in self.file_iterator:
            await net_connection.send(HEADERS.CONTINUE_TRANSFER)

            idx, start, end = big_chunk
            temp_file = FileItem(self.file.path, seeked=start)
            temp_file.size = end
            try:
                await sender.send_big_chunk(temp_file, idx)
                _logger.debug(f"{self._log_prefix} sent big part successfully with {idx=}")
                self._sent_parts[idx] = temp_file
            finally:
                if (
                      not temp_file.seeked == temp_file.size
                ):  # a case when transfer is returned before completely sending the file
                    # adding the failed chunk to failed list so that the another pair get associated for this chunk
                    self.failed_chunks.append(big_chunk)
                    _logger.debug(
                        f"{self._log_prefix} failed to send big part "
                        f"with {idx=}, exiting loop",
                        exc_info=True,
                    )
                    del self.connections[index]
                    break

        await net_connection.send(HEADERS.END_OF_TRANSFER)

    async def __aexit__(self, exec_type, exec_val, exec_tb):
        if exec_type == TransferIncomplete:
            self.task_group.create_task(bomb())

        try:
            await self.task_group.close()
        except (CancelTransfer, TransferIncomplete) as exp:
            if self.state == TransferState.ABORTING:
                _logger.debug("transfer aborting, suppressing:", exc_info=exp)
                return True
            _logger.debug("transfer failed:", exc_info=exp)
            raise

    async def resume_transfer(self):
        raise NotImplementedError

    async def cancel(self):
        self.should_stop = True
        self.state = TransferState.ABORTING
        ct = CancelTransfer("User canceled the transfer")
        self.task_group.cancel_all_tasks(ct)
        await self.status_updater.stop(ct)

    @property
    def id(self):
        return self.transfer_id

    @property
    def current_file(self):
        return self.file

    @property
    def max_noof_parts(self):
        return self.file.size // CHUNK_SIZE + (1 if self.file.size % CHUNK_SIZE else 0)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}"f"("
            f"file={self.file!r}, "
            f"id={self.transfer_id}, "
            f"connections={len(self.connections)}, "
            f"parts={len(self._sent_parts)}, "
            f"total_parts={self.max_noof_parts}, "
            f"state={self.state}"
            f")>"
        )


class _BigChunkReceiver(FReceiver):
    async def recv_big_chunk(self):
        self._expected_exps.clear()
        idx = await self.wrap_exp_handling(net.recv_int, self.net_receiver)
        _logger.debug(f"{self._log_prefix} started  receiving  big chunk={idx}")
        async with aclosing(self.start_transfer()) as loop:
            async for _ in loop:
                pass
        _logger.debug(f"{self._log_prefix} completed receiving big chunk={idx}")

        return idx, self._current_file


class Receiver(
    _CancelMixIn,
    _ControlMixIn,
    AbstractReceiver,
):
    """Receive bigfile from a peer

    Big files often hit the slow speeds barrier due to TCP flow control. bigfile protocol is designed to
    operate with multiple connections to transfer a large file by making it into chunks.

    As soon as a connection is added, it handshakes with sender and start receiving file in multiple parts
    this part size is negotiated or predefined (often the same used by sender)

    Upon receiving all the parts, it finalizes the transfer and merges all the parts written to filesystem into
    one big file with the name received in handshake

    """
    version = const.VERSIONS["FO"]

    async def resume_transfer(self):
        raise NotImplementedError("Bigfile Receiver does not have a resume_transfer method, "
                                  "simply call connection_made to resume broken transfer")

    def __init__(self, peer_obj, transfer_id, download_path, status_updater):
        self._file = None
        self.peer = peer_obj
        self.transfer_id = transfer_id
        self.status_updater = status_updater
        self.connections = {}
        self.parts = {}
        self.state = TransferState.PREPARING
        self.connection_idx_gen = count()
        self.task_group = _BigFileTaskGroup()
        self.should_stop = False
        self._wait_for_first_connection = asyncio.get_running_loop().create_future()
        self.max_chunks = None
        self.download_path = download_path
        self._success_tasks = []  # tasks that completed their transfer successfully
        self._start_transfer = asyncio.Event()  # event to signal the start of transfer

    def connection_made(self, connection):
        if not self._wait_for_first_connection.done():
            self._wait_for_first_connection.set_result(connection)

        _logger.debug(f"{self._log_prefix} adding new connection to receive big chunks {connection=}")

        idx = next(self.connection_idx_gen)
        self.connections[idx] = connection
        self.task_group.create_task(self._receiver_task(connection, idx))

    async def __aenter__(self):
        self.status_updater.status_setup(
            f"{self._log_prefix} receiving file: {self._file}", self._file.seeked, self._file.size
        )
        await self.task_group.__aenter__()
        return self

    async def start_transfer(self):
        conn = await self._wait_for_first_connection
        self.max_chunks = await net.recv_int(conn.recv)

        # agree the transfer handshake
        await conn.send(HEADERS.CONTINUE_TRANSFER)
        _logger.debug(f"{self._log_prefix} transfer handshake sent")
        self.state = TransferState.RECEIVING
        self._start_transfer.set()
        async for status in self.status_updater:
            yield status

    async def _receiver_task(self, connection, conn_idx: int):
        await self._start_transfer.wait()
        if not self.state == TransferState.RECEIVING:
            return

        receiver = _BigChunkReceiver(
            self.peer,
            self.transfer_id,
            self.download_path,
            self.status_updater,
        )
        async with receiver:
            try:
                with self.should_stop:
                    await self.__task_loop(connection, receiver)
            except Exception as exp:
                del self.connections[conn_idx]  # remove ourselves, this decreases active task count
                _logger.debug(f"{self._log_prefix} receiver task failed with:", exc_info=exp)
                raise

        await self.__signal_completion(conn_idx)

    async def __task_loop(self, connection: net.Connection, receiver: _BigChunkReceiver):
        new_file = None
        try:
            what = await connection.recv(1)
            if what == HEADERS.END_OF_TRANSFER:
                return
            idx, new_file = await receiver.recv_big_chunk()
            self.parts[idx] = new_file

        finally:
            if new_file and new_file.seeked < CHUNK_SIZE:
                # this chunk is not completely done
                _logger.debug(
                    f"{self._log_prefix} failed receiving big chunk completely "
                    f"remaining={CHUNK_SIZE - new_file.seeked},"
                    f" removing chunk from system and exiting loop"
                )
                new_file.path.unlink()  # delete the incomplete file
                return

    async def __signal_completion(self, task_idx):
        _logger.debug(f"{self._log_prefix} receiver task={task_idx} completed execution")
        # connection_id is same as task_id
        self._success_tasks.append(task_idx)

        # get the maximum no.of tasks spawned
        # we add connections to self.connections incrementally and python dicts preserve insertion order
        if len(self._success_tasks) == len(self.connections):
            if len(self.parts) == self.max_noof_parts:
                # this means we completed the transfer
                _logger.debug(f"{self._log_prefix} completed receiving big file")
                _logger.debug(f"{self!r}")
                await self.status_updater.close()
                # this signals the start_transfer method to release the iterator

    async def _delete_chunks(self):
        _logger.debug(f"{self._log_prefix} deleting chunks={len(self.parts)}")
        for chunk_item in self.parts.values():
            chunk_item.path.unlink(missing_ok=True)

    async def __aexit__(self, e_type, e_val, e_tb):
        if e_type == TransferIncomplete:
            self.task_group.create_task(bomb())

        ret_value, delete_all = None, False

        try:
            await self.task_group.close()
        except CancelTransfer:
            delete_all = True
            ret_value = True
        else:
            await merge_all_and_delete(self._file, self.parts)

        if e_type == CancelTransfer and self.state == TransferState.ABORTING:
            delete_all = True
            # if we are willingly cancelling the transfer then suppress the error, no need to reraise it
            ret_value = True
        _logger.debug(f"{self._log_prefix} transfer exiting with {ret_value=}, {delete_all=}, {e_val=}", exc_info=e_tb)

        if delete_all:
            await self._delete_chunks()

        return ret_value

    @property
    def max_noof_parts(self):
        # TODO: this or that
        # self._file.size // CHUNK_SIZE + (1 if self._file.size % CHUNK_SIZE else 0)
        return self.max_chunks

    @property
    def id(self):
        return self.transfer_id

    @property
    def current_file(self):
        return self._file

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}"f"("
            f"file={self._file!r}, "
            f"id={self.transfer_id}, "
            f"connections={len(self.connections)}, "
            f"parts={len(self.parts)}, "
            f"total_parts={self.max_chunks}, "
            f"state={self.state}"
            f")>"
        )
