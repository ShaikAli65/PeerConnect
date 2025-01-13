import enum


class HEADERS:
    REQ_FOR_LIST = b"list of users  "
    REDIRECT = b"redirect        "
    SERVER_OK = b"connect accepted"

    CMD_RECV_FILE_AGAIN = b"recv file again "
    CMD_VERIFY_HEADER = b"verify header   "
    CMD_RECV_FILE = b"receive file    "
    CMD_CLOSING_HEADER = b"close connection"
    CMD_TEXT = b"this is message "
    CMD_RECV_DIR = b"cmd to recv dir "
    CMD_FILE_CONN = b"connection for file transfer"
    CMD_DIR_CONN = b'connection for dir transfer'
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
    OTM_UPDATE_STREAM_LINK = "otm_add_stream_link"

    # :todo: Make all these into even/odd to differentiate between signal/data packets


class HANDLE(enum.StrEnum):
    __slots__ = ()
    COMMAND = "this is command "
    SEARCH_RESPONSE = "0result for search name"
    SEND_PEER_LIST_RESPONSE = "0result for send peer list"
    RELOAD = "1this is reload  "
    POP_DIR_SELECTOR = "1pop dir selector"
    OPEN_FILE = "1open file       "
    NEW_PEER = '1new peer'
    REMOVE_PEER = '1remove peer'
    SEARCH_FOR_NAME = "1search name"
    SEND_PROFILES = "1send profiles"
    PEER_LIST = "1this is a profiles list"
    SYNC_USERS = "1sync users"
    CONNECT_USER = "1connect_peer"
    SEND_PEER_LIST = "1send peer list"
    VERIFICATION = "1han verification"
    SET_PROFILE = "1set selected profile"
    TRANSFER_UPDATE = "1transfer update"

    SEND_DIR = "0send_a_directory"
    SEND_FILE = "0send_file_to_peer"
    SEND_TEXT = "0send_text"
    SEND_FILE_TO_MULTIPLE_PEERS = "0send_file_to_multiple_peers"
    SEND_DIR_TO_MULTIPLE_PEERS = "0send_dir_to_multiple_peers"


class REQUESTS_HEADERS:
    __slots__ = ()
    REDIRECT = b"redirect"
    LIST_SYNC = b"sync list"
    ACTIVE_PING = b"Y face like that"
    REQ_FOR_LIST = b"list of users"
    I_AM_ACTIVE = b"com notify user"

    KADEMLIA = b"\x00"
    DISCOVERY = b"\x01"
    GOSSIP = b"\x02"


class DISCOVERY:
    __slots__ = ()
    NETWORK_FIND = b"\x00"
    NETWORK_FIND_REPLY = b"\x01"


class GOSSIP:
    __slots__ = ()
    MESSAGE = "\x00"
    SEARCH_REQ = "\x01"
    SEARCH_REPLY = "\x02"
    CREATE_SESSION = "\x03"
