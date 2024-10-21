import asyncio
import enum
from itertools import count
from pathlib import Path

from src.avails import FileDict, OTMInformResponse, OTMSession, RemotePeer, Wire, WireData, connect, const, dialogs, use
from src.core import Dock, get_this_remote_peer, transfers
from ..avails.connect import get_free_port
from ..core.transfers import FileItem, HEADERS, OTMFilesRelay, PeerFilePool, onetomany


class FileRegistry:
    all_files = FileDict()
    file_counter = count()

    @classmethod
    def get_id_for_file(cls):
        return str(next(cls.file_counter))

    @classmethod
    def get_scheduled_transfer(cls, any_id):
        return cls.all_files.get_scheduled(any_id)

    @classmethod
    def schedule_transfer(cls, key, file_reciever_handle):
        cls.all_files.add_to_scheduled(key, file_reciever_handle)


class State(enum.Enum):
    #
    # remember to reflect changes in `StatusCodes` in fileobject.py
    #
    PREPARING = 1
    CONNECTING = 2
    SENDING = 3
    RECEIVING = 4
    PAUSED = 5
    ABORTING = 6
    COMPLETED = 7


class FileSender:
    version = const.VERSIONS['FO']

    def __init__(self, file_list: list[str | Path], peer_id):
        self.state = State.PREPARING
        self.file_list = [
            transfers.FileItem(x, seeked=0) for x in file_list
        ]
        self.file_handle = None
        self.file_id = FileRegistry.get_id_for_file() + str(peer_id)
        self.peer_obj = Dock.peer_list.get_peer(peer_id)
        self.file_pool = PeerFilePool(
            self.file_list,
            _id=self.file_id,
        )

    async def send_files(self):
        use.echo_print('changing state to connection')  # debug
        self.state = State.CONNECTING
        use.echo_print('sent file header')  # debug
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
            self.state = State.SENDING
            await self.file_pool.send_files(connection.asendall)
        self.state = State.COMPLETED
        print('completed sending')

    async def authorize_connection(self, connection):
        handshake = WireData(
            header=HEADERS.CMD_FILE_CONN,
            _id=get_this_remote_peer().id,
            version=self.version,
            file_id=self.file_id,
        )
        await Wire.send_async(connection, bytes(handshake))
        print("authorization header sent for file connection")

    async def status(self):
        ...

    @property
    def group_count(self):
        return len(self.file_list)


class FileReceiver:

    def __init__(self, data: WireData):
        self.state = State.PREPARING
        self.peer_id = data.id
        self.version_tobe_used = data.version
        self.id = data['file_id']
        loop = asyncio.get_event_loop()
        self.connection_wait = loop.create_future()
        self.connection = None
        self.file_pool = PeerFilePool([], _id=self.id, download_path=const.PATH_DOWNLOAD)
        self.result = None

    async def recv_file(self):
        self.state = State.CONNECTING
        self.connection = await self.get_connection()
        print("got connection")
        self.state = State.RECEIVING
        what, result = await self.file_pool.recv_files(self.connection.arecv)
        self.state = what
        if what == State.COMPLETED:
            self.result = result
        use.echo_print('completed receiving')

    def get_connection(self):
        return self.connection_wait

    def connection_arrived(self, connection):
        self.connection_wait.set_result(connection)


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, dialogs.Dialog.open_file_dialog_window)
    return result


async def send_files_to_peer(peer_id, selected_files):
    # :todo make send_files_to_peer  a generator yielding status to page
    if file_sender_handle := _check_running(peer_id):
        # if any transfer is running just attach FileItems to that transfer
        file_sender_handle.file_pool.attach_files((FileItem(path, 0) for path in selected_files))

    # create a new file sending session
    file_sender = FileSender(selected_files, peer_id)
    FileRegistry.all_files.add_to_current(peer_id=peer_id, file_pool=file_sender)
    await file_sender.send_files()
    FileRegistry.all_files.add_to_completed(peer_id, file_sender)


def _check_running(peer_id) -> FileSender:
    file_handles = FileRegistry.all_files.get_running_file(peer_id)
    return file_handles[0]


def file_recv_request_connection_arrived(connection: connect.Socket, file_req: WireData):
    print("new file connection arrived", file_req['file_id'])
    f = use.wrap_with_tryexcept(file_receiver, file_req, connection)
    asyncio.create_task(f)
    print("scheduling file transfer request", file_req)


async def file_receiver(file_req: WireData, connection):
    """
    Just a wrapper function which does bookeeping for FileReciever object
    """
    file_handle = FileReceiver(file_req)
    FileRegistry.all_files.add_to_current(file_req.id, file_handle)
    await file_handle.recv_file()
    file_handle.connection_arrived(connection)
    FileRegistry.all_files.add_to_completed(file_req.id, file_handle)


def start_new_otm_file_transfer(files: list[Path], peers: list[RemotePeer]):
    file_sender = onetomany.OTMFilesSender(file_list=files, peers=peers, timeout=3)  # check regarding timeouts
    return file_sender


def new_otm_request_arrived(req_data: WireData, addr):
    session = OTMSession(
        originater_id=req_data.id,
        session_id=req_data['session_id'],
        key=req_data['key'],
        fanout=req_data['fanout'],
        link_wait_timeout=req_data['link_wait_timeout'],
        adjacent_peers=req_data['adjacent_peers'],
        file_count=req_data['file_count'],
    )
    passive_endpoint_address = (get_this_remote_peer().ip, get_free_port())
    relay = OTMFilesRelay(
        session,
        passive_endpoint_address,
        get_this_remote_peer().uri
    )
    relay.start_session()
    FileRegistry.schedule_transfer(session.session_id, relay)

    reply = OTMInformResponse(
        peer_id=get_this_remote_peer().id,
        passive_addr=passive_endpoint_address,
        active_addr=get_this_remote_peer().uri,
        session_key=session.key,
    )
    return reply


def update_otm_stream_connection(connection, link_data: WireData):
    session_id = link_data['session_id']
    otm_relay = FileRegistry.get_scheduled_transfer(session_id)
    otm_relay.add_stream_link(connection, link_data)
