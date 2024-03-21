"""Main entry point for the application."""
import tracemalloc

import src.avails.nomad
from src.core import *
from src.core import receivers as nomad, handle_data, handle_signals
from src.core import connectserver as connect_server
from src.core import requests_handler as manage_requests
import src.avails.useables as use
from src.configurations import bootup
from src.managers import endmanager, profile_manager
import src.configurations.configure_app


def initiate() -> int:
    const.OBJ = src.avails.nomad.Nomad(const.THIS_IP, const.PORT_THIS)
    const.OBJ_THREAD = use.start_thread(const.OBJ.commence)
    const.REQUESTS_THREAD = use.start_thread(manage_requests.initiate)
    if connect_server.initiate_connection() is False:
        # error = error_manager.ErrorManager(ConnectionError, "Connection to server failed", 0, __file__)
        # error.resolve()
        # manage_requests.end_requests_connection()
        endmanager.end_session()
        return -1
    # use.start_thread(handle_data_flow.initiate_control).join()

    return 1


if __name__ == "__main__":
    """Entry point for the application when run as a script."""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    bootup.set_paths()
    profile_manager.load_profiles_to_program()
    th = use.start_thread(handle_data.initiate_control)
    use.start_thread(handle_signals.initiate_control)
    const.HOLD_PROFILE_SETUP.wait()
    bootup.initiate()
    src.configurations.configure_app.print_constants()
    # if not bootup.initiate() == 1:
    #     use.echo_print(False, "::CONFIG AND CONSTANTS NOT SET EXITING ... {SUGGESTING TO CHECK ONCE}")
    #     error_log("::CONFIG AND CONSTANTS NOT SET EXITING ...")
    #     exit(0)

    tracemalloc.start()
    initiate()
    th.join()
    activity_log("::End Sequence Complete")
"""

    python -m pip install --upgrade pip
    pip install websockets
    pip install requests
    pip install asyncio
    pip install tqdm
    {set_constants.__name__}()/{set_constants.__code__.co_filename}
"""
"""

{
    admin:{username:admin, password:admin, email:1.1.1.1},
    user:{username:admin, password:admin, email:1.1.1.1},
    guest:{username:admin, password:admin, email:1.1.1.1}
}
"""
