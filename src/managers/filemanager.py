import asyncio
import functools
import itertools
import os
import socket
import struct
from pathlib import Path
import multiprocessing
from typing import Literal

# from typing import

from src.avails import (
    DataWeaver,
    dialogs,
    FileGroup,
    PeerFilePool,
    FileItem,
    FileDict,
    const,
    connect,
    WireData,
    use, RemotePeer,
)

from src.core import peer_list, connections, this_object
from . import submit, FILE, SEND_COMMAND, RECEIVE_COMMAND


all_files = FileDict()


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, dialogs.Dialog.open_file_dialog_window)
    await result

    return result.result()


async def open_dir_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, dialogs.Dialog.open_directory_dialog_window)
    await result

    return result.result()


def get_id_for_file(peer_obj: RemotePeer):
    return peer_obj.get_file_id()


class FileSender:
    version = const.VERSIONS['FO']
    PREPARING = 1
    CONNECTING = 2
    ABORTING = 3
    SENDING = 4
    COMPLETED = 5

    def __init__(self, file_list: list[str | Path]):
        self.state = self.PREPARING
        self.file_list = [FileItem(os.path.getsize(x), x, seeked=0) for x in file_list]
        self.process_handle = None

    async def send_files(self, peer_id):

        peer_obj = peer_list.get_peer(peer_id)
        file_id = get_id_for_file(peer_obj)
        server_sock, addr = self._prepare_socket()
        tell_header = self._prepare_header(addr, file_id)

        self.state = self.CONNECTING

        conn_sock = await connections.Connector.connect_peer(peer_obj)
        await conn_sock.asendall(tell_header)
        conn_sock = await server_sock.aaccept()

        self.state = self.SENDING
        self.process_handle, result = submit(
            asyncio.get_running_loop(),
            FILE,
            self.file_list,
            file_id,
            conn_sock,
            SEND_COMMAND
        )

        result = await result
        self.state = self.COMPLETED
        return result

    def _prepare_header(self, addr, file_id):
        data = WireData(
            header=const.CMD_RECV_FILE,
            _id=this_object.id_encoded,
            version=self.version,
            groups=len(self.file_list),
            file_id=file_id,
            addr=addr,
        ).__bytes__()
        data_size = struct.pack('!I',len(data))
        return data_size + data

    @staticmethod
    def _prepare_socket():
        port = connect.get_free_port()
        main_sock = const.PROTOCOL.create_sync_sock(const.IP_VERSION)
        addr = (this_object.ip, port)
        main_sock.bind(addr)
        return main_sock, addr

    async def status(self):
        ...

    @property
    def group_count(self):
        return len(self.file_list)


class FileReceiver:
    PREPARING = 1
    CONNECTING = 2
    SENDING = 3
    COMPLETED = 4

    def __init__(self, data:WireData):
        self.state = self.PREPARING
        self.peer_id = data.id
        self.group_count = data['groups']
        self.addr = data['addr']

    async def recv_file(self):
        self.state = self.CONNECTING
        sock = await self.prepare_connections()
        # sock.
        ...

    async def prepare_connections(self):
        return await connect.create_connection_async(self.addr)
