import argparse


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
    default=1,
    help="Number of peers (an integer)."
)
parser.add_argument(
    '--mock-multicast',
    type=_str2bool,
    default='f',
    help="Enable mock multicast (True or False)."
)
parser.add_argument(
    '-id',
    default="3",
    help="provide a run-id (directly matches to ip addr)",
)

config = parser.parse_args()

import asyncio
import multiprocessing
import os

import _path  # noqa
from src.__main__ import initiate
from src.avails import RemotePeer
from src.core.app import provide_app_ctx
from src.managers.statemanager import State
from tests import multicast_stub
from tests._initiate import initial_states
from tests.mock import get_mock_app

INSTANCE_ID_OFFSET = 10


@provide_app_ctx
def get_a_peer(app_ctx=None) -> RemotePeer | None:
    try:
        p = next(iter(app_ctx.peer_list))
    except StopIteration:
        print("no peers available")
        return None
    return p


def _process_wrapper(env, *args):
    os.environ.update(env)
    return start_test(*args)


def start_test(*other_states):
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    try:
        mock_app = get_mock_app()
        initiate(initial_states(config, mock_app) + other_states, mock_app)
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

    processes = []
    if config.mock_multicast:
        multicast_process = multiprocessing.Process(target=start_multicast)
        multicast_process.start()
        processes.append(multicast_process)

    if config.test_mode == "local":
        start_test(*states[0])
        return

    if config.peers == 1:
        try:
            _process_wrapper({'INSTANCE_ID': config.id}, *states[0])
        finally:
            [p.join() for p in processes]
        return

    for i in range(len(states)):
        p = multiprocessing.Process(
            target=_process_wrapper,
            name=f"instance-{i + INSTANCE_ID_OFFSET}",
            args=({"INSTANCE_ID": str(i + INSTANCE_ID_OFFSET)}, *states[i]),
        )
        p.start()
        processes.append(p)

    exes = []
    for p in processes:
        try:
            p.join()
        except BaseException as exp:
            exes.append(exp)

    if exes:
        raise BaseExceptionGroup("Multiple Exceptions", exes)


if __name__ == "__main__":
    start_test1(*[tuple()] * config.peers)
