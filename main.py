import asyncio
import os

from src.configurations import bootup
from src.configurations import configure
from src.core import requests, state_handle, connections, PROFILE_WAIT
from src.core.webpage_handlers import pagehandle
from src.managers import profilemanager
from src.managers.statemanager import State
from tests.test import *


def initial_states():
    s1 = State("setpaths", configure.set_paths)
    s2 = State("boot_up initiating", bootup.initiate_bootup)
    s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    s4 = State("launching webpage", pagehandle.initiate_pagehandle)
    s5 = State("waiting for profile choice", PROFILE_WAIT.wait)
    s6 = State("initiating requests", requests.initiate_requests, is_blocking=True)
    s7 = State("initiating comms", connections.initiate_connections, is_blocking=True)

    return s1, s2, s3, s4,  # s5, s6, s7,


async def initiate(states):
    await state_handle.put_states(states)

    await state_handle.process_states()


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    # initial_states = test_initial_states
    const.debug = False
    asyncio.run(initiate(initial_states()), debug=True)
