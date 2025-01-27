import _path  # noqa
from src.core import connectserver
from src.managers.statemanager import State
from tests.test import start_test

if __name__ == "__main__":
    s4 = State("connecting to servers",connectserver.initiate_connection)
    start_test([s4])
