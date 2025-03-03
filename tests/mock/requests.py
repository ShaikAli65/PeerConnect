import asyncio
import functools

from src.avails import const
from src.avails.connect import UDPProtocol
from src.core import requests
from src.core.requests import RequestsEndPoint


def requests_endpoint_mock():
    requests.setup_endpoint = setup_endpoint


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
