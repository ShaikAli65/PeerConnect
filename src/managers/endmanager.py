from typing import Union
from src.avails import constants as const

from src.core import connectserver as connect_server, requests_handler as manage_requests, senders
from src.webpage_handlers import handle_data, handle_signals
from src.managers import filemanager
from src.webpage import httphandler
from src.avails import textobject


def end_session(sig='',frame='') -> Union[bool, None]:
    """
    performs cleanup tasks for ending the application session.

    Returns:
        bool: True if cleanup was successful, False otherwise.
    """

    print("::Initiating End Sequence",sig,frame)
    # activity_log("::Initiating End Sequence")
    textobject.stop_all_text()
    connect_server.end_connection_with_server()
    senders.RecentConnections.end()
    if not const.PAGE_HANDLE_CALL.is_set():
        return None
    if const.HOST_OBJ:
        const.HOST_OBJ.end()
    manage_requests.end_requests_connection()
    handle_data.end()
    handle_signals.end()
    with const.LOCK_LIST_PEERS:
        const.LIST_OF_PEERS.clear()
    httphandler.end_serving()
    filemanager.endFileThreads()
    exit(1)
    # threadmanager.end_all_threads()
