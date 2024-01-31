"""Main entry point for the application."""

import signal
import asyncio
import threading
from avails import constants as const
from core import nomad as nomad
from core import connectserver as connect_server
from core import managerequests as manage_requests
from webpage import handle
from logs import *


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
    connect_server.end_connection()
    await handle.end()
    with const.PRINT_LOCK:
        print("::Page Ended")
    return True


async def _(signum, frame) -> None:
    """Handles ending the application session gracefully upon receiving SIGTERM or SIGINT signals.

    Args:
        signum (int): The signal number.
        frame (FrameType): The current stack frame.
    """

    await asyncio.create_task(end_session_async())


def initiate() -> int:
    """Performs initialization tasks for the application.

    Returns:
        int: 1 on successful initialization, -1 on failure.
    """

    if not const.set_constants():
        with const.PRINT_LOCK:
            print("::CONFIG AND CONSTANTS NOT SET EXITING ... {SUGGESTING TO CHECK ONCE}")
        error_log("::CONFIG AND CONSTANTS NOT SET EXITING ...")
    # try:
    const.OBJ = nomad.Nomad(const.THIS_IP, const.THIS_PORT)
    const.OBJ_THREAD = start_thread(const.OBJ.commence)
    const.REQUESTS_THREAD = start_thread(manage_requests.initiate)
    if connect_server.initiate_connection() is False:
        const.OBJ.end()
        manage_requests.end_connection()
        return -1
    handle.initiate_control()
    # except Exception as e:
    #     e.with_traceback(None)
    #     error_log(f"::Exception in main.py: {e}")
    #     print(f"::Exception in main.py: {e}")
    #     return -1

    return 1


if __name__ == "__main__":
    """Entry point for the application when run as a script."""

    signal.signal(signal.SIGTERM, lambda signum, frame: asyncio.create_task(_(signum, frame)))
    signal.signal(signal.SIGINT, lambda signum, frame: asyncio.create_task(_(signum, frame)))
    initiate()
    activity_log("::End Sequence Complete")


"""
    pip install --upgrade pip
    pip install websockets
    pip install requests
    pip install asyncio
    pip install threading
"""
