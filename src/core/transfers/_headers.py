
class HEADERS:
    CMD_RECV_FILE_AGAIN = b'recv file again '
    CMD_RECV_FILE = b'receive file    '
    CMD_CLOSING_HEADER = b'close connection'
    CMD_TEXT = b'this is message '
    CMD_RECV_DIR = b'cmd to recv dir '
    CMD_RECV_FILE_AND_FORWARD = b'recv file '
    GOSSIP_CREATE_SESSION = b'gossip_session_activate'
    GOSSIP_TREE_CHECK = 'gossip_tree_check'
    GOSSIP_DOWNGRADE_CONN = 'gossip_downgrade_connection'
    GOSSIP_UPGRADE_CONN = 'gossip_upgrade_connection'
    GOSSIP_SESSION_STATE_UPDATE = 'gossip_update_state'
    GOSSIP_UPDATE_STREAM_LINK = 'add_stream_link'
