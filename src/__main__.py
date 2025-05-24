import multiprocessing
import os
import sys
import time
import traceback
from asyncio import CancelledError

from src.avails.useables import COLORS

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.core.app import App, AppType
from src.avails import const
from src.conduit import pagehandle
from src.configurations import bootup, configure
from src.core import acceptor, eventloop, requests
from src.net import connectivity
from src.core.async_runner import AnotherRunner
from src.managers import logmanager, message, profilemanager
from src.managers.statemanager import State, StateManager


def initial_states(app: AppType) -> tuple[State]:
    set_paths = State("set paths", configure.set_paths)
    log_config = State("initiating logging", logmanager.initiate, app)
    load_config = State("loading configurations", configure.load_configs, app)
    load_profiles = State(
        "loading profiles",
        profilemanager.load_profiles_to_program,
        lazy_args=(lambda: app.current_config,)
    )
    launch_webpage = State("launching webpage", bootup.launch_web_page)
    interfaces = State("load interfaces", bootup.load_interfaces, app)
    page_handle = State("initiating page handle", pagehandle.initiate_page_handle, app)

    boot_up = State("boot_up initiating", bootup.set_ip_config, app)

    configure_rm = State(
        "configuring this remote peer object",
        bootup.configure_this_remote_peer,
        app,
    )

    print_config = State("printing configurations", configure.print_app, app.read_only())

    comms = State(
        "initiating comms",
        acceptor.initiate_acceptor,
        lazy_args=(lambda: app,)
    )

    msg_con = State(
        "starting message connections",
        message.initiate,
        app,
    )

    ini_request = State(
        "initiating requests",
        requests.initiate,
        app,
    )

    connectivity_check = State("connectivity checker", connectivity.initiate, app)
    states = locals().copy()
    states.pop('app')
    return tuple(states.values())


cancellation_started = 0.0


async def _async_initiate_helper(states, app):
    await app.state_manager_handle.put_states(states)

    error = None
    async with app.exit_stack:
        try:
            await app.state_manager_handle.process_states()
        except CancelledError as ce:
            error = ce
            # no point of passing cancelled error related to main task into exit_stack
            # (which will be mostly related to keyboard interrupts)

            global cancellation_started
            cancellation_started = time.perf_counter()
        except BaseException as be:
            if const.debug:
                print(COLORS.RED, "CRITICAL EXCEPTION NOT EXPECTING", COLORS.RESET)
                traceback.print_exc()
            error = be

    if error is not None:
        raise error


def initiate(states, app):
    try:
        with AnotherRunner(app_ctx=app.read_only(), debug=const.debug and False) as runner:
            eventloop.set_eager_task_factory()
            app.state_manager_handle = StateManager()
            runner.run(_async_initiate_helper(states, app.read_only()))
    except BaseException as be:
        if const.debug:
            print_str = f"{'-' * 80}\n" \
                        f"## PRINTING TRACEBACK, {const.debug=}\n" \
                        f"{'-' * 80}\n" \
                        f"clean exit completed within {time.perf_counter() - cancellation_started:.6f}s\n"
            be.add_note(print_str)
            raise be

        sys.exit(-1)


if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    multiprocessing.freeze_support()
    initiate(initial_states(App), app=App)
