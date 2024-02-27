from typing import Union
from avails import constants as const

from core import connectserver as connect_server, requests_handler as manage_requests
from webpage import handle


def end_session() -> Union[bool, None]:
    """Asynchronously performs cleanup tasks for ending the application session.

    Returns:
        bool: True if cleanup was successful, False otherwise.
    """

    print("::Initiating End Sequence")
    # activity_log("::Initiating End Sequence")
    connect_server.end_connection_with_server()
    if not const.PAGE_HANDLE_CALL.is_set():
        return None
    if const.OBJ:
        const.OBJ.end()
    manage_requests.end_connection()
    handle.end()
    const.LIST_OF_PEERS.clear()
    # threadmanager.end_all_threads()
    # filemanager.end_file_threads()
    return True
