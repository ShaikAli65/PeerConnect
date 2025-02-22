import enum
from concurrent.futures.thread import ThreadPoolExecutor

from src.transfers._headers import *
from src.transfers.rumor import *

thread_pool_for_disk_io = ThreadPoolExecutor()


class TransferState(enum.Enum):
    PREPARING = 1
    CONNECTING = 2
    SENDING = 3
    RECEIVING = 3
    PAUSED = 5
    ABORTING = 6
    COMPLETED = 7
