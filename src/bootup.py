import asyncio
import logging
import subprocess
import webbrowser
from pathlib import Path

from kademlia.utils import digest

import src.core.async_runner  # noqa
from src.avails import RemotePeer, constants as const, use
from src.conduit import pagehandle
from src.configurations import configure, interfaces as _interfaces
from src.configurations.appconfig import AppConfig, AppRunTime
from src.core import acceptor, peers, requests
from src.managers import ProfileManager, logmanager, message, profilemanager
from src.net import is_wsl_bridged

_logger = logging.getLogger(__name__)


async def set_ip_config(current_profile):
    def clear_logs():
        for path in Path(const.PATH_LOG).glob("*.log*"):
            Path(path).write_text("")

    clear_logs() if const.CLEAR_LOGS else None

    const.THIS_IP = current_profile.interface

    _logger.info(f"setting {current_profile.interface=}")
    return current_profile.interface


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
        status=1
    )
    rp.bind_interface(profile.interface)
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


def _build_local_page_url(app_config:AppConfig) -> str:
    return f"http://localhost:{app_config.page_serve_port}/?port={app_config.page_port}"


async def launch_web_page(app_config):
    try:
        page_url = _build_local_page_url(app_config)
    except (TypeError, ValueError) as exc:
        _logger.fatal(f"cannot launch UI: invalid local page configuration: {exc}")
        return

    if const.IS_LINUX:
        bridged, comment = await is_wsl_bridged()
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


async def init_app(app_runtime: AppRunTime):
    _logger.info("setting paths")
    configure.set_paths()
    _logger.info("initiating logging")
    await logmanager.initiate(app_runtime.exit_stack)

    _logger.info("load interfaces")
    app_runtime.interfaces = await load_interfaces()

    config_map, app_config = await configure.load_configs(app_runtime.exit_stack)
    _logger.info(f"loaded configurations, {app_config=}")

    _logger.info("loading profiles")
    app_runtime.profiles = await profilemanager.load_profiles_to_program(config_map)
    ProfileManager.main_config = config_map

    _logger.info("launching webpage")
    await launch_web_page(app_config)

    _logger.info(f"runtime context {app_runtime=}")

    _logger.info("initiating page handle")
    profile_selection = await pagehandle.initiate_page_handle(app_config, app_runtime)

    _logger.debug("waiting for profile selection")
    current_profile = await profile_selection

    _logger.info("boot_up initiating")
    this_ip = await set_ip_config(current_profile)

    _logger.info("configuring this peer object")
    this_remote_peer = make_this_remote_peer(current_profile)

    _logger.info("printing configurations")
    configure.print_app(this_remote_peer, this_ip, app_config)

    _logger.info("initiating requests")
    req_service, gossip_service, gossip_searcher, discovery_service, kad_server, connectivity = await requests.initiate(
        this_ip,
        this_remote_peer,
        app_runtime,
        app_config,
    )

    peer_service = peers.PeerService(kad_server, gossip_searcher, app_runtime.peer_list)

    _logger.info("initiating comms")
    conn_service = await acceptor.initiate_acceptor(
        app_runtime.exit_stack,
        app_runtime.finalizing,
        app_config,
        this_ip,
        current_profile,
        this_remote_peer,
        peer_service
    )

    _logger.info("starting message connections")
    msg_conn_service = await message.initiate(
        app_runtime,
        this_remote_peer,
        conn_service,
    )
