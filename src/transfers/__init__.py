import enum
from concurrent.futures.thread import ThreadPoolExecutor

from src.net.events import ConnectionEvent
from src.transfers._headers import *
from src.transfers.rumor import *

thread_pool_for_disk_io = ThreadPoolExecutor(thread_name_prefix="transfers-diskio-thread-")

TRANSFER_OK = b'\x01'
TRANSFER_NOT_OK = b'\x00'


class TransferState(enum.Enum):
    PREPARING = 1
    CONNECTING = 2
    SENDING = 3
    RECEIVING = 3
    PAUSED = 5
    ABORTING = 6
    COMPLETED = 7


def make_transfer_id(event: ConnectionEvent) -> str:
    file_req = event.handshake
    return f"{file_req.peer_id};{file_req['transfer_id']}"
