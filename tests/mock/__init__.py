import asyncio
import functools
import getpass
import random
from contextlib import asynccontextmanager

import net.requests
from net.requests import RequestsEndPoint
from src.avails.connect import IPAddress, UDPProtocol

from src.avails import const
from src.conduit import pagehandle, webpage
from src.configurations import interfaces
from src.core.app import provide_app_ctx
from src.managers import ProfileManager, get_current_profile, profilemanager


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
    mock_timeouts()
    print("mocked timeouts")


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

    interfaces.get_interfaces = get_interfaces


@provide_app_ctx
async def profile_getter(ip, *, app_ctx=None):
    p = await ProfileManager.add_profile(
        getpass.getuser(),
        {
            "USER": {
                "name": getpass.getuser() + str(ip),
                "id": random.getrandbits(255),
            },
            "SERVER": {
                "port": 45000,
                "ip": "0.0.0.0",
                "id": 0,
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


async def mock_profile(config):
    if config.test_mode == 'host':
        ip = f"127.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(2, 255)}"
    else:
        ip = None
    await profilemanager.set_current_profile(await profile_getter(ip))


def requests_endpoint_mock():
    net.requests.setup_endpoint = setup_endpoint


async def setup_endpoint(bind_address, multicast_address, req_dispatcher):
    loop = asyncio.get_running_loop()

    base_socket = UDPProtocol.create_async_server_sock(
        loop, bind_address, family=const.IP_VERSION
    )

    transport, _ = await loop.create_datagram_endpoint(
        functools.partial(RequestsEndPoint, req_dispatcher),
        sock=base_socket
    )
    return transport


@asynccontextmanager
async def mock_start_websocket_server():
    yield


def mock_webpage(config):
    if config.test_mode == "host":
        profile = get_current_profile()
        const.WEBSOCKET_BIND_IP = profile.interface.ip

    pagehandle.start_websocket_server = mock_start_websocket_server


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
