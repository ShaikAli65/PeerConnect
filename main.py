"""Main entry point for the application."""

import signal
import asyncio

from avails import constants as const
from core import nomad as nomad
from core import connectserver as connect_server
from core import managerequests as manage_requests
from webpage import handle
from logs import *


async def end_session_async() -> bool:
    """Asynchronously performs cleanup tasks for ending the application session.

    Returns:
        bool: True if cleanup was successful, False otherwise.
    """

    activitylog("::Initiating End Sequence")

    if const.OBJ:
        const.OBJ.end()

    connect_server.end_connection()
    await handle.end()
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
        print("::CONFIG AND CONSTANTS NOT SET EXITING ... {SUGGESTING TO CHECK ONCE}")
        errorlog("::CONFIG AND CONSTANTS NOT SET EXITING ...")
    try:
        const.OBJ = nomad.Nomad(const.THIS_IP, const.THIS_PORT)
        connect_server.initiate_connection()
        const.OBJ_THREAD = const.OBJ.start_thread(const.OBJ.commence)
        const.REQUESTS_THREAD = const.OBJ.start_thread(manage_requests.initiate)
        handle.initiate_control()
    except Exception as e:
        errorlog(f"::Exception in main.py: {e}")
        print(f"::Exception in main.py: {e}")
        return -1

    return 1


if __name__ == "__main__":
    """Entry point for the application when run as a script."""

    signal.signal(signal.SIGTERM, lambda signum, frame: asyncio.create_task(_(signum, frame)))
    signal.signal(signal.SIGINT, lambda signum, frame: asyncio.create_task(_(signum, frame)))
    initiate()
    activitylog("::End Sequence Complete")
