import os
import subprocess
import webbrowser
from pathlib import Path

from kademlia.utils import digest

import src.core.async_runner  # noqa
from src.avails import RemotePeer, constants as const, use
from src.conduit import pagehandle
from src.configurations import interfaces as _interfaces, logger as _logger
from src.core.app import AppType


async def set_ip_config(app_ctx: AppType):
    _clear_logs() if const.CLEAR_LOGS else None

    _logger.debug("waiting for profile selection")

    app_ctx.current_profile = await pagehandle.PROFILE_WAIT

    app_ctx.this_ip = app_ctx.current_profile.interface

    const.THIS_IP = app_ctx.current_profile.interface

    _logger.info(f"{app_ctx.this_ip=}")


def _clear_logs():
    for path in Path(const.PATH_LOG).glob("*.log*"):
        Path(path).write_text("")


async def load_interfaces(app: AppType):
    app.interfaces = _interfaces.get_interfaces()
    _logger.debug(f"loaded interfaces: {app.interfaces=}")


def configure_this_remote_peer(app: AppType):
    rp = _make_this_remote_peer(app.current_profile)
    app.this_remote_peer = rp
    const.USERNAME = rp.username


def _make_this_remote_peer(profile):
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


async def launch_web_page():
    page_url = f"http://localhost:{const.PORT_PAGE_SERVE}/?port={const.PORT_PAGE}"

    try:
        webbrowser.open(page_url)
    except webbrowser.Error:
        if const.IS_WINDOWS:
            os.system(f"start {page_url}")

        elif const.IS_LINUX or const.IS_DARWIN:
            subprocess.Popen(['xdg-open', page_url])
