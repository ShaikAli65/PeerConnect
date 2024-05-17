import os.path
import socket
import threading

from src.core import *
from src.avails.textobject import DataWeaver, SimplePeerText
import src.avails.useables as use
from src.managers import filemanager
from src.trails.test import *
from src.trails.test import _PeerFile

every_file: Dict[str, tuple] = {}


def add_to_list(_id, file_list):
    global every_file
    if every_file.get(str(_id)):
        every_file[str(_id)] += tuple(file_list)
    else:
        every_file[str(_id)] = tuple(file_list)


def sendFile(file_data: DataWeaver, receiver_sock: socket.socket):
    file_list = file_data.content or filemanager.open_file_dialog_window()
    file_groups = make_file_groups(file_list)

    bind_ip = (const.THIS_IP, use.get_free_port())
    hand_shake = DataWeaver(header=const.CMD_RECV_FILE, content={'count': len(file_groups)},
                            _id=bind_ip)
    hand_shake.send(receiver_sock)

    sockets = make_sock_groups(len(file_groups), bind_ip=bind_ip)

    def sock_thread(_file: FiLe, _conn: socket.socket):
        with _conn:
            _file.send_files(_conn)

    file_list = []
    for file_items, conn in zip(file_groups, sockets):
        file = _PeerFile(paths=file_items)
        use.start_thread(_target=sock_thread, _args=(file, conn))
        file_list.append(file)

    add_to_list(file_data.id, file_list)


def fileReceiver(file_data: DataWeaver):
    conn_count = file_data.content['count']
    sockets = make_sock_groups(conn_count, connect_ip=tuple(file_data.id))

    def sock_thread(_file: FiLe, _conn: socket.socket):
        with _conn:
            _file.recv_files(_conn)

    file_list = []
    for conn_sock in sockets:
        file = _PeerFile()
        use.start_thread(_target=sock_thread, _args=(file, conn_sock,))
        file_list.append(file)

    add_to_list(file_data.id, file_list)


if __name__ == "__main__":
    data = DataWeaver(header="", content=[
        "C:\\Users\\7862s\\Desktop\\dslab4.docx",
        "C:\\Users\\7862s\\Downloads\\Telegram Desktop\\P_20220319_193645.jpg",
        "C:\\Users\\7862s\\Downloads\\CiscoPacketTracer_821_Windows_64bit.exe",
        "C:\\Users\\7862s\\Downloads\\bison-2.4.1-setup.exe",
        "C:\\Users\\7862s\\Downloads\\dataspell-2023.2.3.exe",
        "C:\\Users\\7862s\\Downloads\\SamsungDeXSetupWin.exe",
        "C:\\Users\\7862s\\Downloads\\Rainmeter-4.5.17.exe",
        "C:\\Users\\7862s\\Downloads\\jdk-20_windows-x64_bin.msi",
        "C:\\Users\\7862s\\Downloads\\OpenJDK17U-jdk_x64_windows_hotspot_17.0.7_7.msi",
        "C:\\Users\\7862s\\Downloads\\tsetup-x64.4.8.3.exe",
        "D:\\Clips\\20240308_131433.mp4",
        "D:\\Clips\\20240308_132539.mp4",
        "D:\\Clips\\20240308_132643.mp4",
        "D:\\Clips\\20240308_132742.mp4",
        "D:\\Clips\\20240308_132816.mp4",
        "D:\\Clips\\20240308_132838.mp4",
        "D:\\Clips\\20240308_132908.mp4",
        "D:\\Clips\\20240308_133024.mp4",
    ],
        _id=""
    )
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.bind(("localhost",8000))
    s.listen(1)
    reciever_sock, _ = s.accept()
    sendFile(data,reciever_sock)

"""
~ 2,241,524 KB # sending 
-------------------------------------------------
19/1           | 18/2
-------------------------------------------------
6.43 files/s   | 9/9 [00:03<00:00,  2.81 files/s]
               | 9/9 [00:03<00:00,  2.69 files/s]
-------------------------------------------------


~6.89GB # sending 
---------------------------------
13/1           | 13/2
---------------------------------
1.35 files/s   | 7/7 2.24 files/s
               | 6/6 2.23 files/s
---------------------------------

~14GB #sending
----------------------------------
 11/2
----------------------------------
 5/5 [00:18<00:00,  3.60s/ files]
 6/6 [00:32<00:00,  5.46s/ files]
----------------------------------
"""