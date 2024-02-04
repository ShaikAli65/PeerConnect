from core import *
from core import connectserver as connect_server
from core import managerequests as manage_requests
from webpage import handle


def start_thread(_target, args=()):
    if len(args) != 0:
        thread_recv = threading.Thread(target=_target, args=args)
    else:
        thread_recv = threading.Thread(target=_target, daemon=True)
    thread_recv.start()

    return thread_recv


async def end_session_async() -> bool:
    """Asynchronously performs cleanup tasks for ending the application session.

    Returns:
        bool: True if cleanup was successful, False otherwise.
    """

    activity_log("::Initiating End Sequence")

    if const.OBJ:
        const.OBJ.end()
    manage_requests.end_connection()
    connect_server.end_connection_with_server()
    await handle.end()

    return True


async def endSequenceWrapper() -> None:
    """Handles ending the application session gracefully upon receiving SIGTERM or SIGINT signals.
    """

    await end_session_async()


class NotInUse(DeprecationWarning):
    """A class to denote deprecated/not currently used functions/methods/classes"""

    def __init__(self, *args, **kwargs):
        pass
