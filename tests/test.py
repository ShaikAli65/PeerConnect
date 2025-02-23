import argparse
import asyncio
import functools
import multiprocessing
import os
import traceback

import _path  # noqa
from src.__main__ import initiate
from src.avails import RemotePeer
from src.conduit import pagehandle
from src.configurations import bootup, configure
from src.core import acceptor, connectivity, requests
from src.core.public import Dock
from src.managers import get_current_profile, logmanager, message, profilemanager
from src.managers.statemanager import State
from tests import multicast_stub
from tests.mock import mock


def _str2bool(value):
    """
    Convert a string to a boolean.
    Accepts: 'true', 't', 'yes', '1' for True and 'false', 'f', 'no', '0' for False.
    """
    if isinstance(value, bool):
        return value
    lower_value = value.lower()
    if lower_value in {'true', 't', 'yes', '1'}:
        return True
    elif lower_value in {'false', 'f', 'no', '0'}:
        return False
    else:
        raise argparse.ArgumentTypeError("Boolean value expected (True or False).")


parser = argparse.ArgumentParser(
    description="Argument parser for test-mode, peers, and mock-multicast"
)
parser.add_argument(
    '--test-mode',
    choices=['local', 'host'],
    required=True,
    help="Test mode (choose 'local' or 'host')."
)
parser.add_argument(
    '--peers',
    type=int,
    required=True,
    help="Number of peers (an integer)."
)
parser.add_argument(
    '--mock-multicast',
    type=_str2bool,
    required=True,
    help="Enable mock multicast (True or False)."
)

config = parser.parse_args()


def get_a_peer() -> RemotePeer | None:
    try:
        p = next(iter(Dock.peer_list))
    except StopIteration:
        print("no peers available")
        return None
    return p


def test_initial_states():
    set_paths = State("set paths", configure.set_paths)
    log_config = State("initiating logging", logmanager.initiate)
    set_exit_stack = State("setting Dock.exit_stack", bootup.set_exit_stack)
    load_config = State("loading configurations", configure.load_configs)
    load_profiles = State(
        "loading profiles",
        profilemanager.load_profiles_to_program,
        lazy_args=(lambda: Dock.current_config,)
    )
    mock_state = State("mocking", functools.partial(mock, config))

    page_handle = State("initiating page handle", pagehandle.initiate_page_handle, lazy_args=(lambda: Dock.exit_stack,))

    boot_up = State("boot_up initiating", bootup.set_ip_config, lazy_args=(get_current_profile,))

    configure_rm = State(
        "configuring this remote peer object",
        bootup.configure_this_remote_peer,
        lazy_args=(get_current_profile,)
    )

    print_config = State("printing configurations", configure.print_constants)

    comms = State(
        "initiating comms",
        acceptor.initiate_acceptor,
        lazy_args=(lambda: Dock.exit_stack, Dock.dispatchers)
    )

    msg_con = State(
        "starting message connections",
        message.initiate,
        lazy_args=(lambda: Dock.exit_stack, Dock.dispatchers, Dock.finalizing)
    )

    ini_request = State(
        "initiating requests",
        requests.initiate,
        lazy_args=(lambda: Dock.exit_stack, Dock.dispatchers, lambda: Dock.state_manager_handle),
        is_blocking=True
    )

    connectivity_check = State("connectivity checker", connectivity.initiate, lazy_args=(lambda: Dock.exit_stack,))

    # s1 = State("set paths", configure.set_paths)
    # log_config = State("initiating logging", logmanager.initiate)
    # set_exit_stack = State("setting Dock.exit_stack", bootup.set_exit_stack)
    # s2 = State("loading configurations", configure.load_configs)
    # s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    # s5 = State("mocking", functools.partial(mock, config))
    # s4 = State("launching webpage", pagehandle.initiate_page_handle)
    # s6 = State("boot up", bootup.initiate_bootup)
    # s7 = State("configuring this remote peer object", bootup.configure_this_remote_peer)
    # s8 = State("printing configurations", configure.print_constants)
    # s9 = State("initiating requests", requests.initiate)
    # s10 = State("initiating comms", acceptor.initiate_acceptor)
    # s11 = State("connectivity checker", connectivity.initiate)
    return tuple(locals().values())


def start_test(*other_states):
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    try:
        initiate(test_initial_states() + other_states)
    except KeyboardInterrupt:
        return


def start_multicast():
    try:
        asyncio.run(main=multicast_stub.main(config))
    except KeyboardInterrupt:
        return


def start_test1(*states):
    """
    pass tuples of states into function,
    add empty tuples if no states are to be added into process
    spawns len(states) process and unpacks states inside tuples that get added into state sequence
    if test mode is "local" then only the first tuple of states are considered

    Args:
        *states(tuple[State | None]):
    """

    if config.mock_multicast:
        multicast_process = multiprocessing.Process(target=start_multicast)
        multicast_process.start()

    if config.test_mode == "local":
        start_test(*states[0])
        return

    processes = []
    for i in range(len(states)):
        p = multiprocessing.Process(target=start_test, args=states[i])
        p.start()
        processes.append(p)

    print(processes)

    for p in processes:
        try:
            p.join()
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    start_test1(*[tuple()] * config.peers)
