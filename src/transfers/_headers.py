class HEADERS:
    START_TRANSFER = b'\x0f'
    END_OF_TRANSFER = b'\xf0'
    CONTINUE_TRANSFER = b'\xf1'
    FINALIZE_TRANSFER = b'\xff'
    TRANSFER_CONN_OK: bytes = b'\x33'

    REQ_FOR_LIST = b"list of users  "
    REDIRECT = b"redirect        "
    SERVER_OK = b"connect accepted"
    REMOVAL_PING = b"pinging peer for removal"
    PING = b"PING"
    UNPING = b"UN PING"
    CMD_RECV_FILE_AGAIN = b"recv file again "
    CMD_VERIFY_HEADER = b"verify header   "
    CMD_MSG_CONN = b"message connection"

    DUP_MSG_CONN = b"connection already exists"

    MSG_CONN_OK = b"connection ok"
    MSG_ACK = b"msg ack"
    MSG_READ_RECEIPT = b"msg read receipt"

    CMD_RECV_FILE = b"receive file    "
    CMD_CLOSING_HEADER = b"close connection"
    CMD_TEXT = b"this is message "
    CMD_FILE_CONN = b"connection for file transfer"
    CMD_BIG_FILE_CONN = b"connection for big file transfer"
    CMD_DIR_CONN = b"connection for dir transfer"

    GOSSIP_CREATE_SESSION = b"gossip_session_activate"
    GOSSIP_DOWNGRADE_CONN = "gossip_downgrade_connection"
    GOSSIP_UPGRADE_CONN = "gossip_upgrade_connection"
    GOSSIP_SESSION_STATE_UPDATE = "gossip_update_state"
    GOSSIP_UPDATE_STREAM_LINK = "gossip_add_stream_link"
    GOSSIP_LINK_OK = b"OK"
    GOSSIP_TREE_CHECK = "gossip_tree_check"
    GOSSIP_TREE_REJECT = "gossip_tree_reject"
    GOSSIP_TREE_GATHER = "gossip_tree_gather"

    OTM_FILE_TRANSFER = "one to many file transfer request"
    OTM_UPDATE_STREAM_LINK = b"otm_add_stream_link"


class REQUESTS_HEADERS:
    __slots__ = ()
    REDIRECT = b"redirect"
    LIST_SYNC = b"sync list"
    ACTIVE_PING = b"Y face like that"
    REQ_FOR_LIST = b"list of users"
    I_AM_ACTIVE = b"com notify user"


class DISCOVERY:
    __slots__ = ()
    NETWORK_FIND = b"\x00"
    NETWORK_FIND_REPLY = b"\x01"


class GOSSIP_HEADER:
    __slots__ = ()
    MESSAGE = "\x00"
    SEARCH_REQ = "\x01"
    SEARCH_REPLY = "\x02"
    CREATE_SESSION = "\x03"


class BANDWIDTH:
    __slots__ = ()
    CHECK_INITIATE = "\x00"
    REJECTED = "\x01"
