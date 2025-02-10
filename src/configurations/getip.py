"""
    Fallback functions if interfaces module fails somehow
"""

import asyncio
import ipaddress
import json
import re
import socket
import urllib.request

from src.avails import connect, const, use
from src.avails.connect import IPAddress
from src.configurations import logger as _logger


async def get_v4():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as config_socket:
        try:
            config_socket.connect(('1.1.1.1', 80))
            config_ip = config_socket.getsockname()[0]
        except OSError:
            config_ip = socket.gethostbyname(socket.gethostname())
            if const.IS_DARWIN or const.IS_LINUX:
                proc = await asyncio.create_subprocess_exec(
                    "hostname", "-I",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                config_ip = stdout.decode().split(" ")[0]

    return connect.IPAddress(config_ip, -1)


async def get_v6():
    if const.IS_WINDOWS:
        back_up = ipaddress.IPv6Address("::1")
        async for sock_tuple in use.get_addr_info("", None, family=socket.AF_INET6):
            ip, _, _, scope_id = sock_tuple[4]
            ipaddr = ipaddress.IPv6Address(ip)
            if ipaddr.is_link_local:
                return connect.IPAddress(str(ipaddr), scope_id)
        return connect.IPAddress(str(back_up), 0)

    elif const.IS_DARWIN or const.IS_LINUX:
        return next(iter(await get_v6_from_shell()))


async def get_v6_from_shell(include_link_local=True) -> list[IPAddress]:
    proc = await asyncio.create_subprocess_exec(
        'ip', '-6', 'addr', 'show',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Wait for the process to complete and capture output
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        _logger.error(f"Command failed with return code {proc.returncode}: {stderr.decode()}")
        return []

    output_lines = stdout.decode().split('\n')

    ipv6_info = []
    current_ifc_index = None
    current_ifc_name = None

    for line in output_lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        # Check for new interface block
        if re.match(r'^\d+:', stripped_line):
            parts = stripped_line.split(':', 2)
            current_ifc_index = int(parts[0].strip())
            current_ifc_name = parts[1].strip()

        elif 'inet6' in stripped_line:
            # Skip loopback addresses
            if '::1' in stripped_line:
                continue

            if include_link_local is False and 'fe80' in stripped_line:
                continue

            # Extract IPv6 address
            address_part = stripped_line.split()[1].split('/')[0]
            ipv6_info.append(
                connect.IPAddress(
                    address_part,
                    current_ifc_index,
                    current_ifc_name,
                    current_ifc_name
                )
            )

    return ipv6_info


@use.NotInUse
async def get_v6_from_api64():
    def fetch_ip_from_api():
        with urllib.request.urlopen('https://api64.ipify.org?format=json') as response:
            data = response.read().decode('utf-8')
            data_dict = json.loads(data)
            return data_dict.get('ip', '::1')

    try:
        config_ip = await asyncio.to_thread(fetch_ip_from_api)
    except (urllib.request.HTTPError, json.JSONDecodeError):
        config_ip = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6)[0][4][0]
    try:
        config_ip = ipaddress.IPv6Address(config_ip)
    except ValueError:
        _logger.error("cannot get ipv6 address from api64")
        raise
    return connect.IPAddress(config_ip, -1)


@use.NotInUse
def get_v6_from_api64():
    config_ip = "::1"  # Default IPv6 address

    try:
        with urllib.request.urlopen('https://api64.ipify.org?format=json') as response:
            data = response.read().decode('utf-8')
            data_dict = json.loads(data)
            config_ip = data_dict.get('ip', config_ip)
    except (urllib.request.HTTPError, json.JSONDecodeError):
        config_ip = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6)[0][4][0]

    return connect.IPAddress(ipaddress.IPv6Address(config_ip), -1)
