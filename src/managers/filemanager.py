import asyncio
import enum
import os
import struct
from itertools import count
from pathlib import Path

from src.avails import (FileDict, Wire, WireData, connect, const, dialogs, use)
from src.core import Dock, connections, get_this_remote_peer, transfers
from . import processmanager
from ..avails.useables import awaitable
from ..core.transfers import HEADERS, PeerFilePool


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, dialogs.Dialog.open_file_dialog_window)
    return result


class FileRegistry:
    all_files = FileDict()
    file_counter = count()

    @classmethod
    def get_id_for_file(cls):
        return next(cls.file_counter)

    @classmethod
    def get_scheduled_transfer(cls, request_packet):
        pass


def connection_arrived(connection: connect.Socket, data_packet: WireData):

    ...


class STATE(enum.Enum):
    PREPARING = 1
    CONNECTING = 2
    ABORTING = 3
    SENDING = 4
    COMPLETED = 5
    RECEIVING = 6


class FileSender:
    version = const.VERSIONS['FO']

    def __init__(self, file_list: list[str | Path]):
        self.state = STATE.PREPARING
        self.file_list = [transfers.FileItem(os.path.getsize(x), x, seeked=0) for x in file_list]
        self.file_handle = None
        self.file_id = FileRegistry.get_id_for_file()
        self.file_pool = None

    async def send_files(self, peer_id):
        peer_obj = Dock.peer_list.get_peer(peer_id)
        conn_sock = await connections.Connector.connect_peer(peer_obj)
        tell_header = WireData(
            header=HEADERS.CMD_RECV_FILE,
            _id=get_this_remote_peer().id,
            file_id=self.file_id,
            version=self.version,
        )
        await Wire.send_async(conn_sock, bytes(tell_header))
        use.echo_print('changing state to connection')  # debug
        self.state = STATE.CONNECTING
        use.echo_print('sent file header')  # debug
        connection = await connect.connect_to_peer(peer_obj, 0x02,)
        with connection:
            await self.authorize_connection(connection)
            use.echo_print('changing state to sending')  # debug
            self.state = STATE.SENDING
            self.file_pool = PeerFilePool(
                self.file_list,
                _id=self.file_id,
            )
        self.state = STATE.COMPLETED
        print('completed sending')

    async def authorize_connection(self, connection):
        handshake = WireData(
            header=HEADERS.CMD_FILE_CONN,
            _id=get_this_remote_peer().id,
            version=self.version,
            file_id=self.file_id,
        )
        await Wire.send_async(connection,bytes(handshake))

    async def status(self):
        ...

    @property
    def group_count(self):
        return len(self.file_list)


class FileReceiver:

    def __init__(self, data):
        self.state = STATE.PREPARING
        self.peer_id = data.id
        self.group_count = data['groups']
        self.addr = data['addr']
        self.file_id = data['file_id']
        self.file_handle = None
        self.result = None

    async def recv_file(self):
        self.state = STATE.CONNECTING
        conn_sock = await self._prepare_connections()
        self.file_handle, result = processmanager.submit(
            asyncio.get_running_loop(),
            processmanager.FILE,
            None,
            self.file_id,
            conn_sock,
            processmanager.RECEIVE_COMMAND,
        )

        self.state = STATE.RECEIVING
        self.result = await result
        self.state = STATE.COMPLETED
        use.echo_print('completed receiving')

    async def _prepare_connections(self, ):
        return await connect.create_connection_async(self.addr)


def new_file_recv_request(file_req: WireData):
    ...
