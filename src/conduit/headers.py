import enum
from typing import TYPE_CHECKING


@enum.global_enum
class HANDLE(enum.StrEnum):
    __slots__ = ()
    SIGNALS = "1"
    DATA = "0"
    COMMAND = "this is command "
    SEND_PEER_LIST_RESPONSE = "0result for send peer list"
    RELOAD = "1this is reload  "
    POP_DIR_SELECTOR = "1pop dir selector"
    OPEN_FILE = "1open file       "
    NEW_PEER = "1new peer"
    REMOVE_PEER = "1remove peer"
    SEARCH_FOR_NAME = "1search name"
    SEARCH_RESPONSE = "0result for search name"
    GOSSIP_SEARCH = "1gossip search name"
    GOSSIP_SEARCH_RESPONSE = "0result for gossip search name"
    SEND_PROFILES = "1send profiles"
    PEER_LIST = "1this is a profiles list"
    SYNC_USERS = "1sync users"
    CONNECT_USER = "1connect peer"
    SEND_PEER_LIST = "1send peer list"
    VERIFICATION = "1han verification"
    SET_PROFILE = "1set selected profile"
    TRANSFER_UPDATE = "1transfer update"
    FAILED_TO_REACH = "1failed to reach"
    FAILED_TO_SEND = "1failed to send message"
    PEER_CONNECTED = "1connected to peer"
    REQ_PEER_NAME_FOR_DISCOVERY = "1peer name for discovery"
    GET_INTERFACE_CHOICE = "0select interface"
    SEND_DIR = "0send a directory"
    SEND_FILE = "0send file to peer"
    SEND_BIGFILE = "0send big file to peer"
    SEND_TEXT = "0send text"
    RECEIVED_TEXT = "0received text"
    SEND_FILE_TO_MULTIPLE_PEERS = "0send_file_to_multiple_peers"
    SEND_DIR_TO_MULTIPLE_PEERS = "0send_dir_to_multiple_peers"
    REQ_FOR_FILE_TRANSFER = "0a file recv request has been arrived"


if TYPE_CHECKING:
    SIGNALS = "1"
    DATA = "0"
    COMMAND = "this is command "
    SEND_PEER_LIST_RESPONSE = "0result for send peer list"
    RELOAD = "1this is reload  "
    POP_DIR_SELECTOR = "1pop dir selector"
    OPEN_FILE = "1open file       "
    NEW_PEER = '1new peer'
    REMOVE_PEER = '1remove peer'
    SEARCH_FOR_NAME = "1search name"
    SEARCH_RESPONSE = "0result for search name"
    FAILED_TO_SEND = "1failed to send message"
    GOSSIP_SEARCH = "1gossip search name"
    GOSSIP_SEARCH_RESPONSE = "0result for gossip search name"
    SEND_PROFILES = "1send profiles"
    PEER_LIST = "1this is a profiles list"
    SYNC_USERS = "1sync users"
    CONNECT_USER = "1connect_peer"
    SEND_PEER_LIST = "1send peer list"
    VERIFICATION = "1han verification"

    SET_PROFILE = "1set selected profile"
    TRANSFER_UPDATE = "1transfer update"
    FAILED_TO_REACH = "1failed to reach"
    PEER_CONNECTED = "1connected to peer"

    REQ_PEER_NAME_FOR_DISCOVERY = '1peer name for discovery'
    GET_INTERFACE_CHOICE = "0select interface"
    SEND_DIR = "0send_a_directory"
    SEND_FILE = "0send_file_to_peer"
    SEND_BIGFILE = "0send big file to peer"
    SEND_TEXT = "0send_text"

    RECEIVED_TEXT = "0received text"
    SEND_FILE_TO_MULTIPLE_PEERS = "0send_file_to_multiple_peers"
    SEND_DIR_TO_MULTIPLE_PEERS = "0send_dir_to_multiple_peers"
    REQ_FOR_FILE_TRANSFER = "0a file recv request has been arrived"
