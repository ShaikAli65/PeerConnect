import asyncio
from itertools import count
from pathlib import Path

from src.avails import TransfersBookKeeper, OTMInformResponse, OTMSession, RemotePeer, Wire, WireData, connect, const, \
    get_dialog_handler, use
from src.core import Dock, get_this_remote_peer, transfers

from src.avails.connect import get_free_port
from src.core.transfers import FileItem, HEADERS, OTMFilesRelay, PeerFilePool, TransferState, onetomany

transfers_book = TransfersBookKeeper()


class FileSender:
    version = const.VERSIONS['FO']

    def __init__(self, file_list: list[str | Path], peer_id):
        self.state = TransferState.PREPARING
        self.file_list = [
            transfers.FileItem(x, seeked=0) for x in file_list
        ]
        self.file_handle = None
        self._file_id = transfers_book.get_new_id() + str(peer_id)
        self.peer_obj = Dock.peer_list.get_peer(peer_id)
        self.file_pool = PeerFilePool(
            self.file_list,
            _id=self._file_id,
        )

    async def send_files(self):
        use.echo_print('changing state to connection')  # debug
        self.state = TransferState.CONNECTING
        use.echo_print('sent file ')  # debug
        # await asyncio.sleep(0)  # temporarily yielding back
        connection = await connect.connect_to_peer(
            self.peer_obj,
            connect.BASIC_URI,
            timeout=2,
            retries=2,
        )
        with connection:
            await self.authorize_connection(connection)
            use.echo_print('changing state to sending')  # debug
            self.state = TransferState.SENDING
            await self.file_pool.send_files(connection.asendall)
        self.state = TransferState.COMPLETED
        print('completed sending')

    async def authorize_connection(self, connection):
        handshake = WireData(
            header=HEADERS.CMD_FILE_CONN,
            msg_id=get_this_remote_peer().peer_id,
            version=self.version,
            file_id=self._file_id,
        )
        await Wire.send_async(connection, bytes(handshake))
        print("authorization header sent for file connection")

    async def status(self):
        ...

    @property
    def group_count(self):
        return len(self.file_list)

    @property
    def id(self):
        return self._file_id


class FileReceiver:

    def __init__(self, data: WireData):
        self.state = TransferState.PREPARING
        self.peer_id = data.id
        self.version_tobe_used = data.version
        self._file_id = data['file_id']
        loop = asyncio.get_event_loop()
        self.connection_wait = loop.create_future()
        self.connection = None
        self.file_pool = PeerFilePool([], _id=self._file_id, download_path=const.PATH_DOWNLOAD)
        self.result = None

    async def recv_file(self):
        self.state = TransferState.CONNECTING
        self.connection = await self.get_connection()
        print("got connection")
        self.state = TransferState.RECEIVING
        what, result = await self.file_pool.recv_files(self.connection.arecv)
        self.state = what
        if what == TransferState.COMPLETED:
            self.result = result
        use.echo_print('completed receiving')

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
    await file_sender.send_files()
    transfers_book.add_to_completed(peer_id, file_sender)


async def file_recv_request_connection_arrived(connection: connect.Socket, file_req: WireData):
    print("new file connection arrived", file_req['file_id'])
    print("scheduling file transfer request", file_req)
    await file_receiver(file_req, connection)


async def file_receiver(file_req: WireData, connection):
    """
    Just a wrapper function which does bookkeeping for FileReceiver object
    """
    peer_id = file_req.id
    file_handle = FileReceiver(file_req)
    file_handle.connection_arrived(connection)
    transfers_book.add_to_current(file_req.id, file_handle)
    await file_handle.recv_file()
    transfers_book.add_to_completed(file_req.id, file_handle)


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
    use.echo_print(use.COLORS[3], "adding otm session to registry", session.session_id)
    reply = OTMInformResponse(
        peer_id=get_this_remote_peer().peer_id,
        passive_addr=passive_endpoint_address,
        active_addr=get_this_remote_peer().uri,
        session_key=session.key,
    )
    use.echo_print(use.COLORS[3], "replying otm req with", reply.passive_addr, reply.active_addr)
    return bytes(reply)


async def update_otm_stream_connection(connection, link_data: WireData):
    """
    This is the final function call related to an otm session, all other rpc' s from now are made
    internally from/to otm session relay
    """
    use.echo_print(use.COLORS[3], "updating otm connection", connection.getpeername())
    session_id = link_data['session_id']
    otm_relay = transfers_book.get_scheduled(session_id)
    if otm_relay:
        await otm_relay.otm_add_stream_link(connection, link_data)
    else:
        use.echo_print(use.COLORS[3], "otm session not found with id", session_id)
        use.echo_print(use.COLORS[3], "ignoring request from", connection.getpeername())
