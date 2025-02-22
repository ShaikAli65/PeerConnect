import argparse
import asyncio
import functools
import multiprocessing
import os

import _path  # noqa
from src.__main__ import initiate
from src.avails import RemotePeer
from src.conduit import pagehandle
from src.configurations import bootup, configure
from src.core import acceptor, connectivity, requests
from src.core.public import Dock
from src.managers import profilemanager
from src.managers.statemanager import State
from tests import multicast_stub
from tests.mock import mock


def get_a_peer() -> RemotePeer | None:
    try:
        p = next(iter(Dock.peer_list))
    except StopIteration:
        print("no peers available")
        return None
    return p


def test_initial_states():
    s1 = State("set paths", configure.set_paths)
    s2 = State("loading configurations", configure.load_configs)
    s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    s5 = State("mocking", functools.partial(mock, parser.parse_args()))
    s4 = State("launching webpage", pagehandle.initiate_page_handle)
    s6 = State("boot up", bootup.initiate_bootup)
    s7 = State("configuring this remote peer object", bootup.configure_this_remote_peer)
    s8 = State("printing configurations", configure.print_constants)
    s9 = State("initiating requests", requests.initiate)
    s10 = State("initiating comms", acceptor.initiate_acceptor)
    s11 = State("connectivity checker", connectivity.initiate)
    return tuple(locals().values())


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


def start_test(*other_states):
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    try:
        initiate(test_initial_states() + other_states)
    except KeyboardInterrupt:
        return


def start_multicast():
    config = parser.parse_args()
    try:
        asyncio.run(main=multicast_stub.main(config))
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    config = parser.parse_args()

    if config.mock_multicast:
        multicast_process = multiprocessing.Process(target=start_multicast)
        multicast_process.start()

    if config.test_mode == "local":
        start_test()
        exit()

    for _ in range(config.peers):
        multicast_process = multiprocessing.Process(target=start_test)
        multicast_process.start()
