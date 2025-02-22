import logging
import os
import subprocess
import webbrowser
from pathlib import Path

from kademlia.utils import digest

import src.core.async_runner  # noqa
import src.core.eventloop as eventloop
from src.avails import RemotePeer, constants as const, use
from src.avails.connect import IPAddress
from src.configurations import logger as _logger
from src.configurations.interfaces import get_interfaces
from src.core import Dock, set_current_remote_peer_object
from src.managers import get_current_profile, logmanager, profilemanager
from src.webpage_handlers import webpage


async def initiate_bootup():
    eventloop.set_task_factory()
    clear_logs() if const.CLEAR_LOGS else None

    await Dock.exit_stack.enter_async_context(logmanager.initiate())
    const.debug = logging.getLogger().level == logging.DEBUG

    ip_addr = await get_ip()

    # _logger.critical("getting ip interfaces failed, trying fallback options", exc_info=exp)
    # from src.configurations import getip
    # if const.USING_IP_V4:
    #     ip_addr = await getip.get_v4()
    # else:
    #     ip_addr = await getip.get_v6()

    const.THIS_IP = ip_addr
    # const.WEBSOCKET_BIND_IP = const.THIS_IP
    _logger.info(f"{const.THIS_IP=}")


async def get_ip() -> IPAddress:
    interfaces = dict(enumerate(get_interfaces()))
    if const.debug:
        print("-" * 100)
        print(f"interfaces found: \n{"\n".join(str(i) for i in interfaces.values())}")
        print("-" * 100)

    current_profile = profilemanager.get_current_profile()
    assert current_profile is not None, "profile not set exiting"

    default_interface = next(iter(interfaces.values()))

    # Determine if we need to ask user
    current_interface = current_profile.interface
    ask_user = current_interface is None or current_interface.scope_id not in interfaces
    print(f"{current_profile}")
    if not ask_user:
        _logger.info(f"using {(i := interfaces[current_interface.scope_id])}")
        return i

    _logger.debug(f"Previously selected interface {current_interface} not found, re-asking user")
    if (chosen_interface_index := await webpage.ask_for_interface_choice(interfaces)) is not None:
        chosen_interface = interfaces[chosen_interface_index]
        _logger.info(f"using {chosen_interface}")
        # asyncio.create_task()
        await current_profile.write_interface(chosen_interface)
        return chosen_interface

    _logger.info("Using first interface, no choice made")
    return default_interface


def clear_logs():
    for path in Path(const.PATH_LOG).glob("*.log"):
        Path(path).write_text("")


def configure_this_remote_peer():
    rp = make_this_remote_peer()
    set_current_remote_peer_object(rp)
    const.USERNAME = rp.username


def make_this_remote_peer():
    profile = get_current_profile()
    rp = RemotePeer(
        byte_id=digest(profile.id),
        username=profile.username,
        ip=const.THIS_IP.ip,
        conn_port=const.PORT_THIS,
        req_port=const.PORT_REQ,
        status=1,
    )
    return rp


@use.NotInUse
def retrace_browser_path():
    if const.IS_WINDOWS:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice")
        prog_id, _ = winreg.QueryValueEx(key, 'ProgId')
        key.Close()

        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"\\{prog_id}\shell\open\command")
        path, _ = winreg.QueryValueEx(key, '')
        key.Close()

        return path.strip().split('"')[1]

    if const.IS_DARWIN:
        return subprocess.check_output(["osascript",
                                        "-e",
                                        'tell application "System Events" to get POSIX path of (file of process "Safari" as alias)'
                                        ]).decode().strip()

    if const.IS_LINUX:
        command_output = subprocess.check_output(["xdg-settings", "get", "default-web-browser"]).decode().strip()

        if command_output.startswith('userapp-'):
            command_output = subprocess.check_output(["xdg-mime", "query", "default", "text/html"]).decode().strip()

        return command_output


def launch_web_page():
    page_url = os.path.join(const.PATH_PAGE, "index.html")
    try:
        webbrowser.open(page_url)
    except webbrowser.Error:
        if const.IS_WINDOWS:
            os.system(f"start {page_url}")

        elif const.IS_LINUX or const.IS_DARWIN:
            subprocess.Popen(['xdg-open', page_url])

    except FileNotFoundError:
        _logger.critical("::webpage not found, look's like the what you downloaded is corrupted")
