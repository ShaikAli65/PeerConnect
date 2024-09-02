import asyncio
import enum
import os
import struct
from pathlib import Path

from src.avails import (
    dialogs,
    FileItem,
    FileDict,
    const,
    connect,
    WireData,
    use, RemotePeer,
)
from src.core import Dock, connections, get_this_remote_peer
from . import processmanager

all_files = FileDict()


async def open_file_selector():
    loop = asyncio.get_running_loop()
    result = loop.run_in_executor(None, dialogs.Dialog.open_file_dialog_window)
    await result

    return result.result()


def get_id_for_file(peer_obj: RemotePeer):
    return peer_obj.get_file_id()


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
        self.file_list = [FileItem(os.path.getsize(x), x, seeked=0) for x in file_list]
        self.file_handle = None

    async def send_files(self, peer_id):

        peer_obj = Dock.peer_list.get_peer(peer_id)
        file_id = get_id_for_file(peer_obj)
        server_sock, addr = self._prepare_socket()
        tell_header = self._prepare_header(addr, file_id)

        use.echo_print('changing state to connection')  # debug
        self.state = STATE.CONNECTING

        conn_sock = await connections.Connector.connect_peer(peer_obj)
        await conn_sock.asendall(tell_header)
        use.echo_print('sent file header')  # debug
        use.echo_print('waiting for connection', addr)  # debug
        conn_sock, addr = await server_sock.aaccept()
        server_sock.close()
        del server_sock
        use.echo_print('got connection', addr)  # debug
        # conn_sock.set_loop(asyncio.get_running_loop())

        use.echo_print('changing state to sending')  # debug
        self.state = STATE.SENDING
        # :todo: improve this making it a asyncio.task, taking longer time at send_files
        self.file_handle, result = processmanager.submit(
            asyncio.get_running_loop(),
            processmanager.FILE,
            self.file_list,
            file_id,
            conn_sock,
            processmanager.SEND_COMMAND,
        )

        result = await result
        self.state = STATE.COMPLETED
        print('completed sending', result)
        return result

    def _prepare_header(self, addr, file_id):
        data = WireData(
            header=const.CMD_RECV_FILE,
            _id=get_this_remote_peer().id,
            version=self.version,
            groups=len(self.file_list),
            file_id=file_id,
            addr=addr,
        ).__bytes__()
        data_size = struct.pack('!I',len(data))
        return data_size + data

    @staticmethod
    def _prepare_socket() -> tuple[connect.Socket, tuple[str, int]]:
        port = connect.get_free_port()
        main_sock = const.PROTOCOL.create_async_sock(asyncio.get_running_loop(), const.IP_VERSION)
        addr = (get_this_remote_peer().ip, port)
        main_sock.bind(addr)
        main_sock.listen(2)
        return main_sock, addr

    async def status(self):
        ...

    @property
    def group_count(self):
        return len(self.file_list)


class FileReceiver:

    def __init__(self, data:WireData):
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


__all__ = ['FileSender', 'FileReceiver', 'get_id_for_file', 'open_file_selector', 'all_files']
