import asyncio
import os

from src.configurations import bootup, configure
from src.core import Dock, connections, requests
from src.core.webpage_handlers import pagehandle
from src.managers import profilemanager
from src.managers.statemanager import State, StateManager
from src.avails import const


def initial_states():
    s1 = State("set paths", configure.set_paths)
    s2 = State("boot_up initiating", bootup.initiate_bootup)
    s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    s4 = State("printing configurations", configure.print_constants)
    s5 = State("launching webpage", pagehandle.initiate_pagehandle, is_blocking=True)
    s6 = State("waiting for profile choice", Dock.PROFILE_WAIT.wait)
    s7 = State("initiating requests", requests.initiate, is_blocking=True)
    s8 = State("initiating comms", connections.initiate_connections, is_blocking=True)
    return s1, s2, s3, s4, s5, s6, s7, s8


async def initiate(states):
    Dock.state_handle = StateManager()
    await Dock.state_handle.put_states(states)
    await Dock.state_handle.process_states()


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    const.debug = False
    asyncio.run(initiate(initial_states()), debug=True)
