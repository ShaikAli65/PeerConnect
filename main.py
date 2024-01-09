"""Main entry point for the application."""

import signal
import asyncio

from avails import connectserver as connectserver
from core import constants as const, nomad as nomad
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

    connectserver.endconnection()

    if const.SAFELOCKFORPAGE:
        await handle.end()

    return True


async def endsession(signum, frame) -> None:
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
        const.OBJ = nomad.Nomad(const.THISIP, const.THISPORT)
        connectserver.initiate_connection()
        const.OBJTHREAD = const.OBJ.start_thread(const.OBJ.commence)
        handle.initiatecontrol()
    except Exception as e:
        errorlog(f"::Exception in main.py: {e}")
        print(f"::Exception in main.py: {e}")
        return -1

    return 1


if __name__ == "__main__":
    """Entry point for the application when run as a script."""

    signal.signal(signal.SIGTERM, lambda signum, frame: asyncio.create_task(endsession(signum, frame)))
    signal.signal(signal.SIGINT, lambda signum, frame: asyncio.create_task(endsession(signum, frame)))
    initiate()
    activitylog("::End Sequence Complete")
