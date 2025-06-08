import asyncio
import struct
from contextlib import aclosing
from itertools import count

from src import net
from src.avails import const
from src.avails.exceptions import CancelTransfer, InvalidStateError, TransferIncomplete
from src.avails.useables import override, shorten_path
from src.transfers import HEADERS, TransferState, _logger, thread_pool_for_disk_io
from src.transfers.abc import AbstractReceiver, AbstractSender
from src.transfers.status import StatusIterator
from . import FileItemReader, FileItemWriter
from ._fileobject import FileItem
from ._merge import merge_all_and_delete
from .receiver import Receiver as FReceiver
from .sender import Sender as FSender

CHUNK_SIZE = 30 * 1024 * 1024  # 30MB


class _ControlMixIn:
    def pause(self):
        connections = getattr(self, 'connections')
        for i, connection in connections.items():
            connection.send.pause()
            connection.recv.pause()

        _logger.debug(f"{getattr(self, '_log_prefix')} pausing the transfer")
        setattr(self, 'state', TransferState.PAUSED)

    def resume(self):
        connections = getattr(self, 'connections')
        for i, connection in connections.items():
            connection.send.resume()
            connection.recv.resume()

        _logger.debug(f"{getattr(self, '_log_prefix')} resuming the transfer")
        setattr(self, 'state', TransferState.RECEIVING)


class _CancelMixIn:
    async def cancel(self):
        current_state = getattr(self, 'state')
        if current_state == TransferState.CONNECTING:
            _wait_for_first_connection = getattr(self, '_wait_for_first_connection')

            if _wait_for_first_connection.done():
                if _wait_for_first_connection.exception():
                    return  # this is not an expected situation

            setattr(self, 'should_stop', True)
            # TODO: what to do with connection ??
            setattr(self, 'state', TransferState.ABORTING)
            return

        possible_states = (
            TransferState.SENDING,
            TransferState.RECEIVING,
            TransferState.PAUSED,
        )
        if current_state not in possible_states:
            raise InvalidStateError(f"not expected transfer state in {current_state}")

        setattr(self, 'should_stop', True)
        setattr(self, 'state', TransferState.ABORTING)
        ct = CancelTransfer("User canceled the transfer")
        getattr(self, 'task_group').cancel_all_tasks(ct)

        await getattr(self, 'status_updater').stop(
            ct)  # this raises CancelTransfer in the start_transfer method


class _BigFileTaskGroup:
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._closing = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # swallow exceptions here; close() will re-raise if needed
        await self.close()

    def create_task(self, coro, *args, **kwargs):
        if self._closing:
            raise RuntimeError(
                "Cannot create new tasks after closing, call `refresh` to clean up"
            )
        task = asyncio.create_task(coro, *args, **kwargs)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _task_done(self, task: asyncio.Task):
        if not task.cancelled() or task.exception() is None:
            # remove from container if it's a clean exit
            self._tasks.discard(task)
        return

    @property
    def is_stopping(self):
        return self._closing

    def cancel_all_tasks(self, ct=None):
        self._closing = True
        for task in list(self._tasks):
            if not task.done():
                task.cancel(ct)

    async def close(self):
        """Waits for all the tasks to complete and raises exception relevant to transfer"""
        # signal no more tasks and cancel all

        if not self._tasks:
            return

        # wait for all to finish, catching exceptions
        self._closing = True
        results = await asyncio.gather(*self._tasks, return_exceptions=True)
        # pull out actual Exception instances
        exceptions = [r for r in results if isinstance(r, BaseException)]

        # look for your relevant errors
        to_raise = None
        for exc in exceptions:
            if isinstance(exc, ConnectionError):
                to_raise = exc
                break
        if to_raise is None:
            for exc in exceptions:
                # unpack nested args looking for your sentinel types
                for arg in getattr(exc, "args", ()):
                    if isinstance(arg, (TransferIncomplete, CancelTransfer)):
                        to_raise = arg
                        break
                if to_raise:
                    break

        if to_raise:
            raise to_raise

        # TODO: error log all the other suppressed exceptions
        # if there were exceptions but none matched, re-raise the first one
        if exceptions:
            raise exceptions[0]

    def refresh(self):
        # wipe out old tasks and reset
        self._tasks.clear()
        self._closing = False


class _BigChunkSender(FSender):
    def __init__(self, peer_obj, transfer_id, status_updater):
        super().__init__(
            peer_obj,
            transfer_id,
            [],
            status_updater,
        )
        self._big_chunk_id = None
        self._current_part = None

    async def send_big_chunk(self, big_chunk: FileItem, chunk_id):
        self.files_to_send.clear()
        self.files_to_send.append(big_chunk)
        self.should_stop = False
        self.state = TransferState.SENDING
        self._current_file_idx = -1
        self._expected_exps.clear()
        self._current_part = big_chunk
        self._big_chunk_id = chunk_id

        await self.send_file_metadata(big_chunk)
        assert self.current_file is not None

        file_reader = FileItemReader(self.current_file)

        async with aclosing(self.send_one_file(file_reader)) as loop:
            try:
                updater = self.status_updater.write_update  # localize function
                async for bytes_sent in loop:
                    await updater(bytes_sent)
            finally:
                self.current_file.seeked = file_reader.seek_pos
                _logger.debug(
                    f"setting seeked attribute of {self.current_file=}, {file_reader=}"
                )

    @override
    async def send_file_metadata(self, file_item):
        # this function assumes current chunk id matches to part offset
        metadata = struct.pack(
            "!IQQ",
            self._big_chunk_id,
            srt := file_item.seeked - CHUNK_SIZE * self._big_chunk_id,  # start
            stp := file_item.size - CHUNK_SIZE * self._big_chunk_id,  # stop
        )
        t = self._big_chunk_id, srt, stp
        _logger.debug(f"sending big-file-part metadata={t}")
        await self.net_sender(metadata)

    @property
    def current_file(self):
        return self._current_part


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
        self.file: FileItem = file_item
        self.peer = peer_obj
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
        self._wait_for_first_connection: asyncio.Future[net.Connection] = (
            asyncio.get_running_loop().create_future()
        )
        self._start_transfer = asyncio.Event()  # event to signal the start of transfer
        self._on_completion_event = asyncio.Event()  # event to signal end of transfer

    def _bigfile_chunk_generator(self):
        size = self.file.size
        start = 0
        for idx, i in enumerate(range(start, size, CHUNK_SIZE)):
            if len(self.failed_chunks):
                yield self.failed_chunks.pop(0)
            _logger.debug(
                f"{self._log_prefix} yield big chunk({idx=}, start={i}, stop={i + CHUNK_SIZE})"
            )
            yield idx, i, min(size, i + CHUNK_SIZE)

    async def __aenter__(self):
        self.state = TransferState.CONNECTING
        self.status_updater.status_setup(
            f"{self._log_prefix} sending file: {shorten_path(self.file.path, 20)}",
            self.file.seeked,
            self.file.size,
        )
        self.status_updater.freeze()
        await self.task_group.__aenter__()
        return self

    async def start_transfer(self):
        self.state = TransferState.SENDING
        self._start_transfer.set()
        async for update in self.status_updater:
            yield update
        self._on_completion_event.set()

    def connection_made(self, connection):
        if not self._wait_for_first_connection.done():
            self._wait_for_first_connection.set_result(connection)

        _logger.debug(
            f"{self._log_prefix} adding new connection to send big chunks, {connection=}"
        )

        idx = next(self.connection_index_gen)
        self.connections[idx] = connection

        self.task_group.create_task(
            self._spawn_send_task(connection, idx),
            name=f'part-sender-task {idx=}',
        )

    async def _spawn_send_task(self, conn, idx):
        try:
            return await self._send_task(conn, idx)
        finally:
            if len(self._sent_parts) >= self.max_parts_count and len(self.failed_chunks) == 0:
                self.status_updater.unfreeze()
                await self.status_updater.close()

    async def _send_task(self, net_connection, index):
        await self._start_transfer.wait()
        if not self.state == TransferState.RECEIVING:
            return

        sender = _BigChunkSender(self.peer, self.id, self.status_updater)
        sender.connection_made(net_connection)
        _logger.debug(f"{self._log_prefix} starting part sender with {index=}")

        for big_chunk in self.file_iterator:

            idx, start, end = big_chunk
            temp_file = FileItem(self.file.path, seeked=start)
            temp_file.size = end
            try:
                await net_connection.send(HEADERS.CONTINUE_TRANSFER)
                await sender.send_big_chunk(temp_file, idx)
                _logger.debug(
                    f"{self._log_prefix} sent big part successfully with {idx=}, task_id={index}"
                )
                self._sent_parts[idx] = temp_file
                assert await net_connection.recv(1) == HEADERS.TRANSFER_CONN_OK
            finally:
                if (
                      not temp_file.seeked == temp_file.size
                ):  # a case when transfer is returned before completely sending the file
                    # adding the failed chunk to failed list so that the another pair get associated for this chunk
                    self.failed_chunks.append(big_chunk)
                    _logger.debug(
                        f"{self._log_prefix} task={index} failed to send big part "
                        f"with {idx=}, {temp_file.seeked=}, {temp_file.size=}, exiting loop",
                        exc_info=True,
                    )
                    del self.connections[index]
                    break

        await net_connection.send(HEADERS.END_OF_TRANSFER)
        assert (
              await net_connection.recv(1) == HEADERS.FINALIZE_TRANSFER
        ), f"{self._log_prefix} Expecting ACK to be {HEADERS.FINALIZE_TRANSFER=}"
        _logger.debug(
            f"finalizing big-file-part transfer, task={index=} signing off..."
        )

    async def __aexit__(self, exec_type, exec_val, exec_tb):
        self._on_completion_event.set()

        try:
            await self.task_group.close()
        except (CancelTransfer, TransferIncomplete) as exp:
            if self.state == TransferState.ABORTING:
                _logger.debug("transfer aborting, suppressing:", exc_info=exp)
                return True
            _logger.debug("transfer failed:", exc_info=exp)
            raise

    @property
    def done(self):
        return self._on_completion_event

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
    def max_parts_count(self):
        return (self.file.size + CHUNK_SIZE - 1) // CHUNK_SIZE

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}("
            f"file={self.file!r}, "
            f"id={self.transfer_id}, "
            f"connections={len(self.connections)}, "
            f"parts={len(self._sent_parts)}, "
            f"total_parts={self.max_parts_count}, "
            f"state={self.state}"
            f")>"
        )


class _BigChunkReceiver(FReceiver):
    def __init__(self, big_file, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.big_file = big_file  # current big file under transfer

    def _build_file_name(self):
        return f"{self.big_file.path.stem}.{self.id}.{self._big_chunk_id}{const.FILE_ERROR_EXT}"

    @override
    async def _recv_file_item(self):
        raw_meta_data = await self.net_receiver(20)  # 4 + 8 + 8 = 20
        self._big_chunk_id, start, stop = struct.unpack("!IQQ", raw_meta_data)
        file_item = FileItem(self.download_path / self._build_file_name(), start)
        file_item.size = stop
        _logger.debug(
            f"{self._log_prefix} received  big-file-part {file_item!r}, idx={self._big_chunk_id}"
        )
        return file_item

    def _setup_state(self):
        self._current_file = None
        self._expected_exps.clear()
        if self.net_sender is None:
            raise AssertionError("connection not made yet")

    async def recv_big_chunk(self):
        self._setup_state()

        await self._prepare_file_item()
        assert self._current_file is not None

        f_writer = FileItemWriter(self._current_file)
        async with aclosing(self._receive_single_file(f_writer)) as file_receiver:
            try:
                _logger.debug(
                    f"{self._log_prefix} receiving big-file-part data, {f_writer=}"
                )
                u = self.status_updater.write_update
                async for chunk_len in file_receiver:
                    await u(chunk_len)
            finally:
                self._current_file.seeked = f_writer.seek_pos
            _logger.debug(
                f"{self._log_prefix} received big-file-part data, {self._current_file}, {f_writer=}"
            )

        return self._big_chunk_id, self._current_file


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
        raise NotImplementedError(
            "Bigfile Receiver does not have a resume_transfer method, "
            "simply call `connection_made` to resume broken transfer"
        )

    def __init__(self, peer_obj, transfer_id, download_path, status_updater: StatusIterator):
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
        self._completed_tasks = []  # tasks that completed their transfer successfully
        self._start_transfer = asyncio.Event()  # event to signal the start of transfer
        self._on_completion_event = (
            asyncio.Event()
        )  # event to signal the end of transfer

    async def __aenter__(self):
        assert self._file is not None, "set current file to start the transfer"
        self.status_updater.status_setup(
            f"{self._log_prefix} receiving file: {shorten_path(self._file.path, 20)}",
            self._file.seeked,
            self._file.size,
        )
        self.status_updater.freeze()
        await self.task_group.__aenter__()
        return self

    async def start_transfer(self):
        assert self._file is not None, "set current file to start the transfer"

        self.max_chunks = (self._file.size + CHUNK_SIZE - 1) // CHUNK_SIZE
        _logger.debug(f"received part count= {self.max_chunks}")

        self.state = TransferState.RECEIVING
        self._start_transfer.set()
        async for status in self.status_updater:
            yield status
        self._on_completion_event.set()

    def connection_made(self, connection):
        if not self._wait_for_first_connection.done():
            self._wait_for_first_connection.set_result(connection)

        _logger.debug(f"{self._log_prefix} adding new connection to receive big chunks")
        idx = next(self.connection_idx_gen)
        self.connections[idx] = connection

        self.task_group.create_task(
            self._receiver_task(connection, idx), name=f"_receiver_task-{idx=}"
        )

    async def _receiver_task(self, connection, conn_idx: int):
        await self._start_transfer.wait()
        if not self.state == TransferState.RECEIVING:
            return

        receiver = _BigChunkReceiver(
            self.current_file,
            self.peer,
            self.transfer_id,
            self.download_path,
            self.status_updater,
        )
        receiver.connection_made(connection)

        async with receiver:
            try:
                if not self.should_stop:
                    await self.__task_loop(connection, receiver)
            except ConnectionError:
                _logger.debug("connection reset by peer, trying to send FINALIZE flag")
                try:
                    await connection.send(HEADERS.FINALIZE_TRANSFER)
                    _logger.debug(
                        f"sent FINALIZE TRANSFER, parts-recv task id={conn_idx}, signing off..."
                    )
                except ConnectionError:
                    _logger.debug("cannot send FINALIZE flag")
                await self.__signal_completion(conn_idx)
                return
            except Exception as exp:
                del self.connections[
                    conn_idx
                ]  # remove ourselves, this decreases active task count
                _logger.debug(
                    f"{self._log_prefix} receiver task idx={conn_idx} failed with:",
                    exc_info=exp,
                )
                raise

        await connection.send(HEADERS.FINALIZE_TRANSFER)
        _logger.debug(
            f"sent FINALIZE TRANSFER, parts-recv task id={conn_idx}, signing off..."
        )
        await self.__signal_completion(conn_idx)

    async def __task_loop(
          self, connection: net.Connection, receiver: _BigChunkReceiver
    ):
        new_file = None
        while not self.should_stop:
            try:
                what = await connection.recv(1)
                if what == HEADERS.END_OF_TRANSFER:
                    _logger.debug(f"receiving END OF TRANSFER, exiting loop {what=}")
                    break
                assert (
                      what == HEADERS.CONTINUE_TRANSFER
                ), f"continue transfer {what=}, {HEADERS.CONTINUE_TRANSFER=}"
                idx, new_file = await receiver.recv_big_chunk()
                self.parts[idx] = new_file
                await connection.send(HEADERS.TRANSFER_CONN_OK)
            finally:
                if new_file is None:
                    # try getting new_file from part-receiver
                    new_file = receiver.current_file

                if new_file and new_file.seeked < new_file.size:
                    # this chunk is not completely done
                    _logger.debug(
                        f"{self._log_prefix} failed receiving big chunk completely "
                        f"remaining={CHUNK_SIZE - new_file.seeked}, {new_file!r},"
                        f" removing chunk from system and exiting loop"
                    )
                    new_file.path.unlink(missing_ok=True)  # delete the incomplete file
                    break

    async def __signal_completion(self, task_idx):
        _logger.debug(
            f"{self._log_prefix} receiver task={task_idx} completed execution"
        )
        # connection_id is same as task_id
        self._completed_tasks.append(task_idx)

        if len(self.parts) == self.max_chunks:
            # this means we completed the transfer
            _logger.debug(f"{self._log_prefix} completed receiving big file")
            self.state = TransferState.COMPLETED
            _logger.debug(f"{self!r}")
            # this signals the start_transfer method to release the iterator
            self.status_updater.unfreeze()
            await self.status_updater.close()

    async def _delete_chunks(self):
        _logger.debug(f"{self._log_prefix} deleting chunks={len(self.parts)}")
        loop = asyncio.get_running_loop()
        deletes = []
        for chunk_item in self.parts.values():
            t = loop.run_in_executor(
                thread_pool_for_disk_io, chunk_item.path.unlink, True
            )
            deletes.append(t)
        await asyncio.gather(*deletes, return_exceptions=True)

    async def _merge(self):
        if self._file is None:
            _logger.debug(f"{self._log_prefix} root file is None, skipping merge")
            return
        try:
            await merge_all_and_delete(self._file, self.parts)
        except FileNotFoundError as fnf:
            raise TransferIncomplete("File download corrupted") from fnf

    async def __aexit__(self, e_type, e_val, e_tb):

        self.status_updater.unfreeze()
        await self.status_updater.close()
        self._on_completion_event.set()

        if e_type == CancelTransfer and self.state == TransferState.ABORTING:
            # if we are willingly cancelling the transfer then suppress the error, no need to reraise it
            await self._delete_chunks()
            return True

        try:
            await self.task_group.close()
            _logger.info(f"Completed big file transfer {self=}")
            return await self._merge()
        except CancelTransfer:
            await self._delete_chunks()
            return True
        except BaseException:
            await self._merge()
            raise

    def __del__(self):
        # delete all the parts, at this point there is no point in recovering those
        for fi in self.parts.values():
            fi.path.unlink(missing_ok=True)

    @property
    def id(self):
        return self.transfer_id

    @property
    def current_file(self):
        return self._file

    @current_file.setter
    def current_file(self, file):
        self._file = file

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}"
            f"("
            f"file={self._file!r}, "
            f"id={self.transfer_id}, "
            f"connections={len(self.connections)}, "
            f"parts={len(self.parts)}, "
            f"total_parts={self.max_chunks}, "
            f"state={self.state}"
            f")>"
        )

    @property
    def done(self):
        return self._on_completion_event
