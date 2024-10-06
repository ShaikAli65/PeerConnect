
class HEADERS:
    REQ_FOR_LIST = b'list of users  '
    REDIRECT = b'redirect        '
    SERVER_OK = b'connect accepted'

    CMD_RECV_FILE_AGAIN = b'recv file again '
    CMD_VERIFY_HEADER = b'verify header   '
    CMD_RECV_FILE = b'receive file    '
    CMD_CLOSING_HEADER = b'close connection'
    CMD_TEXT = b'this is message '
    CMD_RECV_DIR = b'cmd to recv dir '
    CMD_FILE_CONN = b'connection for file transfer'

    GOSSIP_CREATE_SESSION = b'gossip_session_activate'
    GOSSIP_TREE_CHECK = 'gossip_tree_check'
    GOSSIP_DOWNGRADE_CONN = 'gossip_downgrade_connection'
    GOSSIP_UPGRADE_CONN = 'gossip_upgrade_connection'
    GOSSIP_SESSION_STATE_UPDATE = 'gossip_update_state'
    GOSSIP_UPDATE_STREAM_LINK = 'add_stream_link'

    # :todo: Make all these into even/odd to differentiate between signal/data packets

    HANDLE_COMMAND = 'this is command '
    HANDLE_SEARCH_RESPONSE = 'result for search name'
    HANDLE_SEND_PEER_LIST_RESPONSE = 'result for send peer list'
    HANDLE_RELOAD = 'this is reload  '
    HANDLE_POP_DIR_SELECTOR = 'pop dir selector'
    HANDLE_OPEN_FILE = 'open file       '
    HANDLE_SEARCH_FOR_NAME = '\x01search name'
    HANDLE_SEND_PROFILES = '\x01send profiles'
    HANDLE_SYNC_USERS = '\x01sync users      '
    HANDLE_CONNECT_USER = '\x01connect_peer'
    HANDLE_SEND_PEER_LIST = '\x01send peer list'
    HANDLE_VERIFICATION = '\x01han verification'
    HANDLE_SET_PROFILE = '\x01set selected profile'

    HANDLE_SEND_DIR = '\x00send_a_directory'
    HANDLE_SEND_FILE = '\x00send_file_to_peer'
    HANDLE_SEND_TEXT = '\x00send_text'
    HANDLE_SEND_FILE_TO_MULTIPLE_PEERS = '\x00send_file_to_multiple_peers'
    HANDLE_SEND_DIR_TO_MULTIPLE_PEERS = '\x00send_dir_to_multiple_peers'
