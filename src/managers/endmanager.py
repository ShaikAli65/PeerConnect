from typing import Union
from src.avails import constants as const

from src.core import connectserver as connect_server, requests_handler as manage_requests, senders, handle_data, \
    handle_signals
from src.webpage import httphandler


def end_session() -> Union[bool, None]:
    """Asynchronously performs cleanup tasks for ending the application session.

    Returns:
        bool: True if cleanup was successful, False otherwise.
    """

    print("::Initiating End Sequence")
    # activity_log("::Initiating End Sequence")
    connect_server.end_connection_with_server()
    senders.RecentConnections.end()
    if not const.PAGE_HANDLE_CALL.is_set():
        return None
    if const.OBJ:
        const.OBJ.end()
    manage_requests.end_requests_connection()
    handle_data.end()
    handle_signals.end()
    with const.LOCK_LIST_PEERS:
        const.LIST_OF_PEERS.clear()
    httphandler.end_serving()
    exit(1)
    # threadmanager.end_all_threads()
    # filemanager.endFileThreads()
