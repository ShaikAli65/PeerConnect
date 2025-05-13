from src.__main__ import initial_states as main_states
from src.managers.statemanager import State
from tests.mock import mock


def initial_states(config, app):
    _states = list(main_states(app))
    removes = {"launching webpage", "loading profiles"}

    for state in _states.copy():
        if state.name in removes:
            _states.remove(state)
    mock_state = State("mocking test functions", mock, config)
    _states.insert(3, mock_state)
    return tuple(_states)
