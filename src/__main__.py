import os
import sys
import time
import traceback
from asyncio import CancelledError

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    sys.path.append(os.getcwd())  # TODO: make this an environment variable

from src.avails import const
from src.conduit import pagehandle
from src.configurations import bootup, configure
from src.core import acceptor, connectivity, eventloop, requests
from src.core.async_runner import AnotherRunner
from src.core.public import Dock
from src.managers import logmanager, message, profilemanager
from src.managers.statemanager import State, StateManager


def initial_states():
    set_paths = State("set paths", configure.set_paths)
    log_config = State("initiating logging", logmanager.initiate)
    set_exit_stack = State("setting Dock.exit_stack", bootup.set_exit_stack)
    load_config = State("loading configurations", configure.load_configs)
    load_profiles = State("loading profiles", profilemanager.load_profiles_to_program)
    launch_webpage = State("launching webpage", pagehandle.initiate_page_handle)
    profile_choice = State("waiting for profile choice", pagehandle.PROFILE_WAIT.wait)
    boot_up = State("boot_up initiating", bootup.initiate_bootup)
    configure_rm = State("configuring this remote peer object", bootup.configure_this_remote_peer)
    print_config = State("printing configurations", configure.print_constants)
    comms = State("initiating comms", acceptor.initiate_acceptor)
    msg_con = State("starting message connections", message.initiate)
    ini_request = State("initiating requests", requests.initiate, is_blocking=True)
    connectivity_check = State("connectivity checker", connectivity.initiate)

    return tuple(locals().values())


def initiate(states):
    cancellation_started = 0.0

    async def _async_initiate():

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
            eventloop.set_eager_task_factory()
            runner.run(_async_initiate())
    except KeyboardInterrupt:
        if const.debug:
            traceback.print_exc()
            print_str = f"{"-" * 80}\n" \
                        f"## PRINTING TRACEBACK, {const.debug=}\n" \
                        f"{"-" * 80}\n" \
                        f"clean exit completed within {time.perf_counter() - cancellation_started:.6f}s\n"
            print(print_str)

        exit(0)


if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    initiate(initial_states())
