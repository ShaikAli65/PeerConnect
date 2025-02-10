import os
import time
import traceback
from asyncio import CancelledError

from src.avails import const
from src.configurations import bootup, configure
from src.core import Dock, acceptor, connectivity, requests
from src.core.async_runner import AnotherRunner
from src.managers import profilemanager
from src.managers.statemanager import State, StateManager
from src.webpage_handlers import pagehandle


def initial_states():
    s1 = State("set paths", configure.set_paths)
    s2 = State("loading configurations", configure.load_configs)
    s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    s4 = State("launching webpage", pagehandle.initiate_page_handle)
    # s5 = State("waiting for profile choice", pagehandle.PROFILE_WAIT.wait)
    s6 = State("boot_up initiating", bootup.initiate_bootup)
    s7 = State("configuring this remote peer object", bootup.configure_this_remote_peer)
    s8 = State("printing configurations", configure.print_constants)
    s9 = State("initiating comms", acceptor.initiate_acceptor, is_blocking=True)
    s10 = State("initiating requests", requests.initiate, is_blocking=True)
    s11 = State("connectivity checker", connectivity.initiate)

    return tuple(locals().values())


def initiate(states):
    cancellation_started = 0.0

    async def _initiate():
        Dock.state_manager_handle = StateManager()
        await Dock.state_manager_handle.put_states(states)

        cancelled = None
        async with Dock.exit_stack:
            try:
                await Dock.state_manager_handle.process_states()
            except CancelledError as ce:
                cancelled = ce
                # no point of passing cancelled error related to main task (which will be mostly related to keyboard interrupts)
                # into exit_stack
                nonlocal cancellation_started
                cancellation_started = time.perf_counter()

        if cancelled:
            raise cancelled

    try:
        with AnotherRunner(debug=const.debug) as runner:
            runner.run(_initiate())
    except KeyboardInterrupt:
        if const.debug:
            traceback.print_exc()
            print("-"*80)
            print(f"## PRINTING TRACEBACK, {const.debug=}")
            print("-"*80)
            elapsed = time.perf_counter() - cancellation_started
            print(f"clean exit completed within {elapsed:.6f}s")

        exit(0)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    initiate(initial_states())
