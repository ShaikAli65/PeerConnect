"""Main entry point for the application."""
import tracemalloc
import signal
import platform

import src.core.nomad
from src.core import *
from src.webpage_handlers import handle_data, handle_signals
from src.core import connectserver as connect_server
from src.core import requests_handler as manage_requests
import src.avails.useables as use
from src.configurations import boot_up
from src.managers import endmanager, profile_manager
import src.configurations.configure_app


def initiate() -> int:
    const.HOST_OBJ = src.core.nomad.Nomad(const.THIS_IP, const.PORT_THIS)
    const.OBJ_THREAD = use.start_thread(const.HOST_OBJ.commence)
    const.REQUESTS_THREAD = use.start_thread(manage_requests.initiate)
    if connect_server.initiate_connection() is False:
        endmanager.end_session()
        return -1
    return 1


if __name__ == "__main__":
    """Entry point for the application when run as a script."""
    # print("USE TEMPFILE MODULE IN DIRECTORYMANAGER")
    # exit(1)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    const.SYS_NAME = platform.system()
    boot_up.set_paths()
    boot_up.initiate()
    profile_manager.load_profiles_to_program()
    th = use.start_thread(handle_data.initiate_control)
    use.start_thread(handle_signals.initiate_control)
    const.HOLD_PROFILE_SETUP.wait()
    if const.END_OR_NOT is True:
        exit(1)
    src.configurations.configure_app.print_constants()
    tracemalloc.start()
    initiate()
    signal.signal(signalnum=signal.SIGINT, handler=endmanager.end_session)
    th.join()
    activity_log("::End Sequence Complete")
"""

    python -m pip install --upgrade pip
    pip install websockets
    pip install requests
    pip install asyncio
    pip install tqdm
    {x.__name__}()\\{os.path.relpath(x.__code__.co_filename)
"""
"""

{
    admin:{username:admin, password:admin, email:1.1.1.1},
    user:{username:admin, password:admin, email:1.1.1.1},
    guest:{username:admin, password:admin, email:1.1.1.1}
}
"""
