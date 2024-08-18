import asyncio
import time

from src.avails import const, RemotePeer
from src.configurations import configure, bootup
from src.core import connectserver
from src.core.peers import set_current_remote_peer_object
from src.managers import profilemanager
from src.managers.statemanager import State
from src.managers import filemanager

from src.core import peers


def test():
    const.SERVER_IP = const.THIS_IP
    const.PORT_SERVER = 45000
    configure.print_constants()
    set_current_remote_peer_object(RemotePeer('test', 'localhost'))
    print(peers.get_this_remote_peer())


async def test_file():
    peer = RemotePeer('test', '::1', 45000, 8089, 1)
    peer_list.add_peer(peer)
    file_list = [
        # "C:\\Users\\7862s\\Downloads\\pycharm-community-2024.1.2.exe",
        # "C:\\Users\\7862s\\Downloads\\DiscordSetup.exe",
        # "D:\\Schindlers List 1993 720p UHD BluRay x264 6CH-Pahe.mkv",
        # "C:\\Users\\7862s\\Downloads\\Lab3.pdf",
        # "C:\\Users\\7862s\\Downloads\\Wireshark-4.2.4-x64.exe",
        # "C:\\Users\\7862s\\Downloads\\bison-2.4.1-src.zip",
        # "C:\\Users\\7862s\\Downloads\\bison-2.4.1-setup.exe",
        "C:\\Users\\7862s\\Downloads\\ns-allinone-3.41.tar.bz2",
        "C:\\Users\\7862s\\Downloads\\NDP481-Web.exe",
        "C:\\Users\\7862s\\Downloads\\CiscoPacketTracer_821_Windows_64bit.exe",
        "D:\\loki\\S1\\Loki.S01E1.2021.2160p.HDR10Plus.DSNP.WEB-DL.x265.ENG-HIN.DDP5.1.HEVC_ShiNobi_.mkv",
    ]

    sender = filemanager.FileSender(file_list)
    fut = asyncio.create_task(sender.send_files(peer_id=peer.id))
    sender = filemanager.FileSender(file_list)
    fut = asyncio.create_task(sender.send_files(peer_id=peer.id))
    sender = filemanager.FileSender(file_list)
    fut = asyncio.create_task(sender.send_files(peer_id=peer.id))
    sender = filemanager.FileSender(file_list)
    fut = asyncio.create_task(sender.send_files(peer_id=peer.id))
    sender = filemanager.FileSender(file_list)
    fut = asyncio.create_task(sender.send_files(peer_id=peer.id))


def test_initial_states():
    s1 = State("setpaths", configure.set_paths)

    s2 = State("boot_up initiating", bootup.initiate_bootup)
    s5 = State("adding shit", test)

    s3 = State("loading profiles", profilemanager.load_profiles_to_program)
    # s4 = State("connecting to servers",connectserver.initiate_connection)
    # s4 = State("connecting to servers",connectserver.initiate_connection)
    # s4 = State("checking file transfers", test_file)

    def add_state():
        s = State("new state",func=lambda: print("inside state"))
        state_handle.state_queue.put_nowait(s)

    s4 = State("adding state", add_state)

    return s1, s2, s5, s3, s4,
