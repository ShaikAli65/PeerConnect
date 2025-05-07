import argparse
import asyncio
import multiprocessing
import os
import traceback

import _path  # noqa
from src.__main__ import initial_states, initiate
from src.avails import RemotePeer
from src.core.app import App, provide_app_ctx
from src.managers.statemanager import State
from tests import multicast_stub


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
    default=2,
    help="Number of peers (an integer)."
)
parser.add_argument(
    '--mock-multicast',
    type=_str2bool,
    default='t',
    help="Enable mock multicast (True or False)."
)

config = parser.parse_args()


@provide_app_ctx
def get_a_peer(app_ctx=None) -> RemotePeer | None:
    try:
        p = next(iter(app_ctx.peer_list))
    except StopIteration:
        print("no peers available")
        return None
    return p


def test_initial_states(app):
    states = list(initial_states(app))
    removes = {"launching webpage", "loading profiles"}

    for state in states.copy():
        if state.name in removes:
            states.remove(state)

    return tuple(states)


def start_test(*other_states):
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    try:
        initiate(test_initial_states(App) + other_states, App)
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
