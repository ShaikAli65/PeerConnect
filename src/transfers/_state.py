import enum

class TransferState(enum.Enum):
    PREPARING = 1
    CONNECTING = 2
    SENDING = 3
    RECEIVING = 3
    PAUSED = 5
    ABORTING = 6
    COMPLETED = 7
