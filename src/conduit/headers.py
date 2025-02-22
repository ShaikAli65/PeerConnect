import enum
from typing import TYPE_CHECKING


@enum.global_enum
class HANDLE(enum.StrEnum):
    __slots__ = ()
    SIGNALS = "1"
    DATA = "0"
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
    FAILED_TO_REACH = "1failed to reach"

    REQ_PEER_NAME_FOR_DISCOVERY = '1get a peer name for discovery'
    GET_INTERFACE_CHOICE = "0select interface"
    SEND_DIR = "0send_a_directory"
    SEND_FILE = "0send_file_to_peer"
    SEND_TEXT = "0send_text"
    SEND_FILE_TO_MULTIPLE_PEERS = "0send_file_to_multiple_peers"
    SEND_DIR_TO_MULTIPLE_PEERS = "0send_dir_to_multiple_peers"
    REQ_FOR_FILE_TRANSFER = "0a file recv request has been arrived"


if TYPE_CHECKING:
    SIGNALS = "1"
    DATA = "0"

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
    REQ_PEER_NAME_FOR_DISCOVERY = '1get a peer name for discovery'
    SEND_DIR = "0send_a_directory"
    SEND_FILE = "0send_file_to_peer"
    SEND_TEXT = "0send_text"
    SEND_FILE_TO_MULTIPLE_PEERS = "0send_file_to_multiple_peers"
    SEND_DIR_TO_MULTIPLE_PEERS = "0send_dir_to_multiple_peers"
    REQ_FOR_FILE_TRANSFER = "0a file recv request has been arrived"
    FAILED_TO_REACH = "1failed to reach"
    GET_INTERFACE_CHOICE = "0select interface"
