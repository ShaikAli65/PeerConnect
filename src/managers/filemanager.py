import asyncio
import enum
from itertools import count
from pathlib import Path

from src.avails import FileDict, Wire, WireData, connect, const, dialogs, use
from src.core import Dock, get_this_remote_peer, transfers
from ..core.transfers import HEADERS, PeerFilePool


class FileRegistry:
    all_files = FileDict()
    file_counter = count()

    @classmethod
    def get_id_for_file(cls):
        return str(next(cls.file_counter))

    @classmethod
    def get_scheduled_transfer(cls, request_packet):
        return cls.all_files.get_scheduled(request_packet['file_id'])

    @classmethod
    def schedule_transfer(cls, file_reciever_handle):
        cls.all_files.add_to_scheduled(file_reciever_handle)


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, dialogs.Dialog.open_file_dialog_window)
    return result


def file_recv_request_connection_arrived(connection: connect.Socket, file_req: WireData):
    print("new file connection arrived", file_req['file_id'])
    file_handle = FileReceiver(file_req)
    f = use.wrap_with_tryexcept(file_handle.recv_file)
    asyncio.create_task(f)
    print("scheduling file transfer request", file_handle.id)
    file_handle.connection_arrived(connection)


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
        await Wire.send_async(connection,bytes(handshake))
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
    