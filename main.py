"""Main entry point for the application."""

import signal
import tracemalloc
from avails import constants as const
import avails.useables as use
from core import nomad as nomad
from core import configure_app
from core import connectserver as connect_server
from core import requestshandler as manage_requests
from webpage import handle
from logs import *


def initiate() -> int:
    """Performs initialization tasks for the application.

    Returns:
        int: 1 on successful initialization, -1 on failure.
    """

    if not configure_app.set_constants():
        with const.PRINT_LOCK:
            print("::CONFIG AND CONSTANTS NOT SET EXITING ... {SUGGESTING TO CHECK ONCE}")
        error_log("::CONFIG AND CONSTANTS NOT SET EXITING ...")
    # try:
    const.OBJ = nomad.Nomad(const.THIS_IP, const.THIS_PORT)
    const.OBJ_THREAD = use.start_thread(const.OBJ.commence)
    const.REQUESTS_THREAD = use.start_thread(manage_requests.initiate)
    if connect_server.initiate_connection() is False:
        # error = error_manager.ErrorManager(ConnectionError, "Connection to server failed", 0, __file__)
        # error.resolve()
        const.OBJ.end()
        manage_requests.end_connection()
        return -1
    use.start_thread(handle.initiate_control).join()
    # except Exception as e:
    #     e.with_traceback(None)
    #     error_log(f"::Exception in main.py: {e}")
    #     print(f"::Exception in main.py: {e}")
    #     return -1

    return 1


if __name__ == "__main__":
    """Entry point for the application when run as a script."""
    # try:
    tracemalloc.start()
    signal.signal(signal.SIGTERM, lambda signum, frame: use.endSequenceWrapper())
    signal.signal(signal.SIGINT, lambda signum, frame: use.endSequenceWrapper())
    initiate()
    activity_log("::End Sequence Complete")
    # except RuntimeError as re:
    #     error_log(f'::RuntimeError in main.py exp: {re}')
    # finally:
    #     exit(0)

"""
    pip install --upgrade pip
    pip install websockets
    pip install requests
    pip install asyncio
    pip install threading
"""
