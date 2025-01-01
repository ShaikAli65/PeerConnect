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

    HANDLE_COMMAND = "this is command "
    HANDLE_SEARCH_RESPONSE = "result for search name"
    HANDLE_SEND_PEER_LIST_RESPONSE = "result for send peer list"
    HANDLE_RELOAD = "this is reload  "
    HANDLE_POP_DIR_SELECTOR = "pop dir selector"
    HANDLE_OPEN_FILE = "open file       "

    HANDLE_SEARCH_FOR_NAME = "1search name"
    HANDLE_SEND_PROFILES = "1send profiles"
    HANDLE_PEER_LIST = "1this is a profiles list"
    HANDLE_SYNC_USERS = "1sync users      "
    HANDLE_CONNECT_USER = "1connect_peer"
    HANDLE_SEND_PEER_LIST = "1send peer list"
    HANDLE_VERIFICATION = "1han verification"
    HANDLE_SET_PROFILE = "1set selected profile"

    HANDLE_SEND_DIR = "0send_a_directory"
    HANDLE_SEND_FILE = "0send_file_to_peer"
    HANDLE_SEND_TEXT = "0send_text"
    HANDLE_SEND_FILE_TO_MULTIPLE_PEERS = "0send_file_to_multiple_peers"
    HANDLE_SEND_DIR_TO_MULTIPLE_PEERS = "0send_dir_to_multiple_peers"


class REQUESTS_HEADERS:
    __slots__ = ()
    REDIRECT = b"redirect        "
    LIST_SYNC = b"sync list       "
    ACTIVE_PING = b"Y face like that"
    REQ_FOR_LIST = b"list of users  "
    I_AM_ACTIVE = b"com notify user"

    KADEMLIA = b"\x00"
    DISCOVERY = b"\x01"
    GOSSIP = b"\x02"


class DISCOVERY:
    NETWORK_FIND = b"\x00"
    NETWORK_FIND_REPLY = b"\x01"


class GOSSIP:
    __slots__ = ()
    MESSAGE = b"\x00"
    SEARCH_REQ = b"\x01"
    SEARCH_REPLY = b"\x02"
    CREATE_SESSION = b"\x03"
