import asyncio
import builtins
import os
import time

import select
import signal
from threading import Thread

from src.avails import const, RemotePeer
from src.configurations import bootup
from src.configurations import configure
from src.core import connectserver, requests, state_handle, connections, PROFILE_WAIT, peers
from src.core.webpage_handlers import pagehandle
from src.managers.statemanager import State
from src.managers import profilemanager


def initial_states():
    s1 = State("setpaths", configure.set_paths)
    s2 = State("boot_up initiating", bootup.initiate_bootup)
    s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    s4 = State("launching webpage", pagehandle.initiate_pagehandle)
    s5 = State("waiting for profile choice", PROFILE_WAIT.wait)
    s6 = State("initiating requests", requests.initiate_requests, is_blocking=True)
    s7 = State("initiating comms", connections.initiate_connections, is_blocking=True)

    return s1, s2, s3, s4, s5, s6, s7,


def test():
    const.SERVER_IP = const.THIS_IP
    const.PORT_SERVER = 45000
    configure.print_constants()


def test_initial_states():
    s1 = State("setpaths", configure.set_paths)
    s2 = State("boot_up initiating", bootup.initiate_bootup)
    s5 = State("adding shit", test)

    s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    s4 = State("connecting to servers",connectserver.initiate_connection)

    return s1, s2,s5, s3, s4,


async def initiate(states):
    await state_handle.put_states(states)

    await state_handle.process_states()


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(initiate(test_initial_states()))
