"""Main entry point for the application."""
import tracemalloc
import signal

from src.avails.remotepeer import RemotePeer
from src.core import *
import src.configurations.configure_app
import src.avails.useables as use
from src.core.nomad import Nomad
from src.webpage_handlers import handle_data, handle_signals
from src.core import connectserver as connect_server
from src.core import requests_handler as manage_requests
from src.configurations import boot_up
from src.managers import endmanager, profile_manager


def initiate() -> int:
    const.HOST_OBJ = Nomad(const.THIS_IP, const.PORT_THIS)
    # const.OBJ_THREAD = use.start_thread(const.HOST_OBJ.initiate)
    const.OBJ_THREAD = threading.Thread(target=const.HOST_OBJ.initiate)
    const.OBJ_THREAD.start()
    const.REQUESTS_THREAD = use.start_thread(manage_requests.initiate)
    # connect_server.initiate_connection()
    if connect_server.initiate_connection() is None:
        endmanager.end_session()
        return -1
    const.OBJ_THREAD.join()
    return 1


if __name__ == "__main__":
    """Entry point for the application when run as a script."""
    #        ITERTOOLS
    #        FUNCTOOLS
    #         LOGGING
    #         ASYNCIO
    #          HTTP
    #         WEBRTC

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    src.configurations.configure_app.set_paths()
    boot_up.initiate()
    profile_manager.load_profiles_to_program()
    boot_up.initiate_this_object()
    use.start_thread(handle_data.initiate_control)
    use.start_thread(handle_signals.initiate_control)
    const.HOLD_PROFILE_SETUP.wait()
    if const.END_OR_NOT is True:
        exit(1)
    const.THIS_OBJECT = RemotePeer(const.USERNAME, const.THIS_IP, const.PORT_THIS, report=const.PORT_REQ, status=1)

    src.configurations.configure_app.print_constants()
    tracemalloc.start()
    signal.signal(signalnum=signal.SIGINT, handler=endmanager.end_session)
    initiate()
    activity_log("::End Sequence Complete")
"""
    python -m pip install --upgrade pip
    pip install websockets
    pip install tqdm
"""

"""
{
    admin:{username:admin, password:admin, email:1.1.1.1},
    user:{username:admin, password:admin, email:1.1.1.1},
    guest:{username:admin, password:admin, email:1.1.1.1}
}
"""
