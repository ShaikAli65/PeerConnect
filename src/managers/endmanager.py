from src.avails import constants as const

from src.core import connectserver as connect_server, requests_handler, senders
from src.webpage_handlers import handle_data, handle_signals, httphandler
from src.managers import filemanager, directorymanager, thread_manager
from src.avails import textobject, remotepeer


def end_session(sig='',frame=''):
    """
    performs cleanup tasks for ending the application session.

    Returns:
        bool: True if cleanup was successful, False otherwise.
    """
    const.END_OR_NOT = True
    print("::Initiating End Sequence",sig,frame)
    # activity_log("::Initiating End Sequence")
    connect_server.end_connection_with_server()
    requests_handler.end_requests_connection()
    senders.RecentConnections.end()

    # if not const.PAGE_HANDLE_CALL.is_set():
    #     return None
    if const.HOST_OBJ:
        const.HOST_OBJ.end()
    handle_data.end()
    handle_signals.end()
    # httphandler.end_serving()
    directorymanager.end_zipping_processes()
    filemanager.endFileThreads()
    textobject.stop_all_text()
    remotepeer.end()
    thread_manager.thread_handler.signal_stopping()
    exit(1)
