import asyncio
import functools
import getpass
import logging
import os
import random
import socket
from contextlib import asynccontextmanager

import src.core.app
from src.avails import const
from src.conduit import pagehandle, webpage
from src.configurations import interfaces
from src.configurations.interfaces import get_interfaces
from src.managers import ProfileManager, get_current_profile, profilemanager
from src.net import IPAddress, UDPProtocol, requests


def get_mock_app():
    from src.managers.statemanager import StateManager
    from src.core.app import App
    return App


async def mock(config):
    # print('*' * 80, get_mock_app().current_config)
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
    # requests_endpoint_mock()
    print("mocked request endpoint")
    mock_timeouts()
    print("mocked timeouts")
    remove_logging_to_file()


def mock_interface_selector():
    async def mock_selector(_interfaces):
        i = None
        for i, inter in _interfaces.items():
            if 'wi' in inter.friendly_name.lower():
                return i

        return i

    webpage.ask_for_interface_choice = mock_selector


def mock_interfaces(config):
    def get_interfaces() -> list[IPAddress]:
        return [profilemanager.get_current_profile().interface]

    if config.test_mode == "local":
        return
    from src.conduit import handleprofiles
    handleprofiles.get_interfaces = get_interfaces
    interfaces.get_interfaces = get_interfaces


@src.core.app.provide_app_ctx
async def profile_getter(ip, *, app_ctx=None):
    p = await ProfileManager.add_profile(
        getpass.getuser(),
        {
            "USER": {
                "name": getpass.getuser() + str(ip),
                "id": random.getrandbits(255),
            },
            "INTERFACE": {
                "ip": ip,
                "scope_id": -1,
                "if_name": b'{TEST}',
                "friendly_name": "testing",
            } if ip else {}
        }
    )

    async def delete(*_):
        await ProfileManager.delete_profile(p.file_name)

    app_ctx.exit_stack.push_async_exit(delete)
    return p


@src.core.app.provide_app_ctx
async def mock_profile(config, app_ctx):
    ProfileManager.main_config = app_ctx.current_config
    if config.test_mode == 'host':
        n = os.environ.get('INSTANCE_ID', random.randint(0, 255))
        ip = f"127.{n}.{n}.{n}"
    else:
        ip = None
        for ip in get_interfaces():
            if 'wi' in ip.friendly_name:
                break
    print("setting current profile")
    await profilemanager.set_current_profile(await profile_getter(ip))
    pagehandle.PROFILE_WAIT = asyncio.get_running_loop().create_future()
    pagehandle.PROFILE_WAIT.set_result(profilemanager.get_current_profile())


async def setup_endpoint(bind_address, multicast_address, req_dispatcher, app_ctx):
    from src.net.requests import RequestsEndPoint
    loop = asyncio.get_running_loop()

    base_socket = UDPProtocol.create_async_server_sock(
        loop, bind_address, family=const.IP_VERSION
    )
    base_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        transport, _ = await loop.create_datagram_endpoint(
            functools.partial(RequestsEndPoint, req_dispatcher, app_ctx),
            sock=base_socket
        )
    except OSError as oe:
        oe.add_note(f"ADDR : {bind_address}")
        raise oe

    return transport


requests.setup_endpoint.__code__ = setup_endpoint.__code__


@asynccontextmanager
async def mock_start_websocket_server():
    yield


def mock_webpage(config):
    if config.test_mode == "host":
        profile = get_current_profile()
        const.WEBSOCKET_BIND_IP = profile.interface.ip

    pagehandle.start_websocket_server = mock_start_websocket_server

    from src.conduit import webpage

    async def get_transfer_ok(*args, **kwargs):
        return True

    async def send_profiles_and_get_updated_profiles(profiles, *_):
        return profiles

    webpage.get_transfer_ok.__code__ = get_transfer_ok.__code__
    webpage.send_profiles_and_get_updated_profiles.__code__ = send_profiles_and_get_updated_profiles.__code__


def mock_multicast_addr(config):
    if config.test_mode == 'host':
        if const.USING_IP_V4:
            const.MULTICAST_IP_v4 = '127.0.0.1'
            const.PORT_NETWORK = 4000


def mock_timeouts():
    const.DISCOVER_TIMEOUT = 1  # quick and responsive in testing
    const.PING_TIME_CHECK_WINDOW = 1

    const.TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK = 100
    const.PING_TIMEOUT = 100
    const.DEFAULT_TRANSFER_TIMEOUT = 100


def remove_logging_to_file():
    logger = logging.getLogger()
    h = logging.getHandlerByName('queue_handler')
    logger.removeHandler(h)
    logger = logging.getLogger('src.core.discover')
    h = logging.getHandlerByName('discovery_handler')
    logger.removeHandler(h)
