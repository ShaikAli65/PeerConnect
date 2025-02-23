from tests.mock import constants
from tests.mock.discovery import mock_multicast_addr
from tests.mock.interface import mock_interface_selector, mock_interfaces
from tests.mock.profile import mock_profile
from tests.mock.requests import requests_endpoint_mock
from tests.mock.webpage import mock_webpage


async def mock(config):
    await mock_profile(config)
    print("profile mocked")
    mock_webpage(config)
    print("mocked webpage")
    mock_interfaces(config)
    print("mocked interfaces")
    mock_interface_selector()
    print("mocked interface selector")
    mock_multicast_addr(config)
    print("mocked multicast addr")
    requests_endpoint_mock()
    print("mocked request endpoint")
    constants.mock_timeouts()
    print("mocked timeouts")
