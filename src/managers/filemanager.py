import asyncio
import contextlib
import logging
import socket
import traceback
from pathlib import Path

from src.avails import OTMInformResponse, OTMSession, RemotePeer, TransfersBookKeeper, Wire, WireData, connect, const, \
    get_dialog_handler, use
from src.avails.connect import get_free_port
from src.avails.events import ConnectionEvent
from src.avails.exceptions import TransferIncomplete
from src.core import Dock, get_this_remote_peer, transfers
from src.core.transfers import FileItem, HEADERS, OTMFilesRelay, PeerFilePool, TransferState, onetomany

transfers_book = TransfersBookKeeper()

_logger = logging.getLogger(__name__)


class FileSender:
    version = const.VERSIONS['FO']

    def __init__(self, file_list: list[str | Path], peer_id):
        self.state = TransferState.PREPARING
        self.file_list = [
            transfers.FileItem(x, seeked=0) for x in file_list
        ]
        self.socket = None
        self._file_id = transfers_book.get_new_id() + str(peer_id)
        self.peer_obj = Dock.peer_list.get_peer(peer_id)
        self.file_pool = PeerFilePool(
            self.file_list,
            _id=self._file_id,
        )

    async def send_files(self):
        _logger.info('changing state to connection', extra={'id': self._file_id})  # debug
        self.state = TransferState.CONNECTING
        async with self._prepare_socket() as self.socket:
            _logger.info('changing state to sending', extra={'id': self._file_id})
            self.state = TransferState.SENDING
            try:
                await self.file_pool.send_files(self.socket.asendall)
            except ConnectionResetError as cre:
                _logger.error("got connection reset, pausing transfer", exc_info=cre)
                self.state = TransferState.PAUSED
                raise
        _logger.info('completed sending', extra={'id': self.id})

        self.state = TransferState.COMPLETED

    @contextlib.asynccontextmanager
    async def _prepare_socket(self):
        with await connect.connect_to_peer(
            self.peer_obj,
            connect.CONN_URI,
            timeout=2,
            retries=2,
        ) as connection:
            connection.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 1)
            await self.authorize_connection(connection)
            yield connection

    async def authorize_connection(self, connection):
        handshake = WireData(
            header=HEADERS.CMD_FILE_CONN,
            msg_id=get_this_remote_peer().peer_id,
            version=self.version,
            file_id=self._file_id,
        )
        await Wire.send_async(connection, bytes(handshake))
        _logger.debug("authorization header sent for file connection", extra={'id': self._file_id})

    async def status(self):
        ...

    @property
    def group_count(self):
        return len(self.file_list)

    @property
    def id(self):
        return self._file_id


class FileReceiver:

    def __init__(self, peer_id, file_id, version):
        self.state = TransferState.PREPARING
        self.peer_id = peer_id
        self.version_tobe_used = version
        self._file_id = file_id
        loop = asyncio.get_event_loop()
        self.connection_wait = loop.create_future()
        self.connection = None
        self.file_pool = PeerFilePool([], _id=self._file_id, download_path=const.PATH_DOWNLOAD)
        self.result = None

    async def recv_file(self):
        self.state = TransferState.CONNECTING
        self.connection = await self.get_connection()
        _logger.debug(f"got connection {self._file_id=}")
        self.state = TransferState.RECEIVING

        try:
            self.state = await self.file_pool.receive_file_loop(self.connection.arecv)
        except TransferIncomplete as ti:
            if ti.args[0] == TransferState.PAUSED:
                self.state = TransferState.PAUSED
                _logger.debug(f'paused receiving: {self.file_pool}')
                return

        if self.state == TransferState.COMPLETED:
            _logger.info(f'completed receiving: {self.file_pool}')
        elif self.state == TransferState.PAUSED:
            _logger.debug(f'paused receiving: {self.file_pool}')

    def get_connection(self):
        return self.connection_wait

    def connection_arrived(self, connection):
        self.connection_wait.set_result(connection)

    @property
    def id(self):
        return self._file_id


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_dialog_handler().open_file_dialog_window)
    return result


async def send_files_to_peer(peer_id, selected_files):
    # :todo make send_files_to_peer a generator or a status iterator yielding status to page
    if file_sender_handle := transfers_book.check_running(peer_id):
        # if any transfer is running just attach FileItems to that transfer
        file_sender_handle.file_pool.attach_files((FileItem(path, 0) for path in selected_files))
        return

    # create a new file sending session
    file_sender = FileSender(selected_files, peer_id)
    transfers_book.add_to_current(peer_id=peer_id, transfer_handle=file_sender)
    try:
        await file_sender.send_files()
    except OSError as oe:
        if file_sender.state == TransferState.PAUSED:
            transfers_book.add_to_continued(peer_id, file_sender)
        _logger.error("failed to send files to peer", exc_info=oe)

    if (file_sender.state == TransferState.COMPLETED) or (file_sender.state == TransferState.ABORTING):
        transfers_book.add_to_completed(peer_id, file_sender)


async def file_receiver(file_req: WireData, connection):
    """
    Just a wrapper function which does bookkeeping for FileReceiver object
    """
    peer_id = file_req.id
    version = file_req.version
    file_transfer_id = file_req['file_id']

    file_handle = FileReceiver(peer_id, file_transfer_id, version)
    file_handle.connection_arrived(connection)

    transfers_book.add_to_current(file_req.id, file_handle)
    await file_handle.recv_file()
    if file_handle.state == TransferState.COMPLETED:
        transfers_book.add_to_completed(file_req.id, file_handle)
    if file_handle.state == TransferState.PAUSED:
        transfers_book.add_to_continued(file_req.id, file_handle)


def start_new_otm_file_transfer(files: list[Path], peers: list[RemotePeer]):
    file_sender = onetomany.OTMFilesSender(file_list=files, peers=peers, timeout=3)  # check regarding timeouts
    transfers_book.add_to_scheduled(file_sender.session.session_id, file_sender.relay)
    return file_sender


def new_otm_request_arrived(req_data: WireData, addr):
    session = OTMSession(
        originate_id=req_data.id,
        session_id=req_data['session_id'],
        key=req_data['key'],
        fanout=req_data['fanout'],
        link_wait_timeout=req_data['link_wait_timeout'],
        adjacent_peers=req_data['adjacent_peers'],
        file_count=req_data['file_count'],
        chunk_size=req_data['chunk_size'],
    )
    passive_endpoint_address = (get_this_remote_peer().ip, get_free_port())
    relay = OTMFilesRelay(
        session,
        passive_endpoint_address,
        get_this_remote_peer().uri
    )
    f = use.wrap_with_tryexcept(relay.start_read_side)
    asyncio.create_task(f())
    transfers_book.add_to_scheduled(session.session_id, relay)
    _logger.info("adding otm session to registry", extra={'id': session.session_id})
    reply = OTMInformResponse(
        peer_id=get_this_remote_peer().peer_id,
        passive_addr=passive_endpoint_address,
        active_addr=get_this_remote_peer().uri,
        session_key=session.key,
    )
    _logger.info(f"replying otm req with passive={reply.passive_addr} active={reply.active_addr}")
    return bytes(reply)


def FileConnectionHandler():
    async def handler(event: ConnectionEvent):
        with event.transport.socket:
            file_req = event.handshake
            _logger.info("new file connection arrived", extra={'id': file_req['file_id']})
            _logger.debug(f"scheduling file transfer request {file_req!r}")
            try:
                await file_receiver(file_req, event.transport.socket)
            except Exception as e:
                print(e)
                traceback.print_exc()

    return handler


def OTMConnectionHandler():
    async def handler(event: ConnectionEvent):
        """
        This is the final function call related to an otm session, all other rpc' s from now are made
        internally from/to otm session relay
        """
        connection = event.transport.socket
        link_data = event.handshake
        _logger.info("updating otm connection", extra={'addr': connection.getpeername()})
        session_id = link_data['session_id']
        otm_relay = transfers_book.get_scheduled(session_id)
        if otm_relay:
            await otm_relay.otm_add_stream_link(connection, link_data)
        else:
            _logger.error("otm session not found with id", extra={'session id': session_id})
            _logger.error("ignoring request from", extra={'addr': connection.getpeername()})

    return handler
