import asyncio
import logging
import subprocess
import webbrowser
from pathlib import Path

from kademlia.utils import digest

import src.core.async_runner  # noqa
from src import net
from src.avails import RemotePeer, constants as const, use
from src.configurations import interfaces as _interfaces

_logger = logging.getLogger(__package__)


async def set_ip_config(current_profile):
    _clear_logs() if const.CLEAR_LOGS else None

    const.THIS_IP = current_profile.interface

    _logger.info(f"setting {current_profile.interface=}")
    return current_profile.interface

def _clear_logs():
    for path in Path(const.PATH_LOG).glob("*.log*"):
        Path(path).write_text("")


async def load_interfaces():
    interfaces = _interfaces.get_interfaces()
    _logger.debug(f"loaded interfaces: {interfaces=}")
    return interfaces


def make_this_remote_peer(profile):
    rp = RemotePeer(
        byte_id=digest(profile.id),
        username=profile.username,
        ip=profile.interface.ip,
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


def _build_local_page_url() -> str:
    page_serve_port = int(const.PORT_PAGE_SERVE)
    page_port = int(const.PORT_PAGE)
    return f"http://localhost:{page_serve_port}/?port={page_port}"


async def launch_web_page():
    try:
        page_url = _build_local_page_url()
    except (TypeError, ValueError) as exc:
        _logger.fatal(f"cannot launch UI: invalid local page configuration: {exc}")
        return

    if const.IS_LINUX:
        bridged, comment = await net.is_wsl_bridged()
        if bridged:
            _logger.info(f"detected wsl, launching page through powershell: {comment}")
            await _open_page_in_win_shell(page_url)
            return
        if bridged is False:
            _logger.fatal(f"cannot launch UI: {comment}")
            return

    try:
        webbrowser.open(page_url)
    except webbrowser.Error:
        if const.IS_WINDOWS:
            await _open_page_in_win_shell(page_url)

        elif const.IS_LINUX or const.IS_DARWIN:
            p = await asyncio.create_subprocess_exec('xdg-open', page_url)
            await p.wait()


async def _open_page_in_win_shell(page_url):
    p = await asyncio.create_subprocess_exec(
        'cmd.exe',
        '/c',
        'start',
        '',
        page_url
    )
    await p.wait()
