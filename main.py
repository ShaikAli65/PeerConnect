"""Main entry point for the application."""
import tracemalloc
from src.core import *
from src.core import configure_app

from src.core import receivers as nomad
from src.core import connectserver as connect_server
from src.core import requests_handler as manage_requests
import src.avails.useables as use
from src.webpage import handle_data


def initiate() -> int:
    """Performs initialization tasks for the application.

    Returns:
        int: 1 on successful initialization, -1 on failure.
    """

    # try:
    const.OBJ = nomad.Nomad(const.THIS_IP, const.PORT_THIS)
    const.OBJ_THREAD = use.start_thread(const.OBJ.commence)
    const.REQUESTS_THREAD = use.start_thread(manage_requests.initiate)
    if connect_server.initiate_connection() is False:
        # error = error_manager.ErrorManager(ConnectionError, "Connection to server failed", 0, __file__)
        # error.resolve()
        const.OBJ.end()
        manage_requests.end_requests_connection()
        return -1
    use.start_thread(handle_data.initiate_control).join()
    # except Exception as e:
    #     e.with_traceback(None)
    #     error_log(f"::Exception in main.py: {e}")
    #     print(f"::Exception in main.py: {e}")
    #     return -1

    return 1


if __name__ == "__main__":
    """Entry point for the application when run as a script."""
    # try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if not configure_app.set_constants():
        with const.LOCK_PRINT:
            print("::CONFIG AND CONSTANTS NOT SET EXITING ... {SUGGESTING TO CHECK ONCE}")
        error_log("::CONFIG AND CONSTANTS NOT SET EXITING ...")
        exit(0)

    tracemalloc.start()
    initiate()
    activity_log("::End Sequence Complete")
    # except RuntimeError as re:
    #     error_log(f'::RuntimeError in main.py exp: {re}')
    # finally:
    #     exit(0)

"""

    python -m pip install --upgrade pip
    pip install websockets
    pip install requests
    pip install asyncio
    pip install tqdm
    
"""
