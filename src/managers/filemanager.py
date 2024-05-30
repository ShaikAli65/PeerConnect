import os.path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog
from concurrent.futures import ThreadPoolExecutor

from src.avails.container import FileDict
from src.core import *
from src.avails.remotepeer import RemotePeer
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.avails.fileobject import FiLe, make_file_groups, make_sock_groups, PeerFilePool

global_files = FileDict()


def fileSender(file_data: DataWeaver, receiver_sock):
    file_list = file_data.content['files']
    receiver_id = file_data.id
    if file_list == ['']:
        file_list = open_file_dialog_window()
    if not file_list:
        return

    # print("got to send ",file_data)  # debug

    def _sock_thread(_id, _file: FiLe, _conn):
        with _conn:
            if _file.send_files(_conn):
                global_files.add_to_completed(_id, _file)
            else:
                global_files.add_to_continued(_id, _file)

    file_groups = make_file_groups(file_list, grouping_level=file_data.content['grouping_level'])
    file_pools = [PeerFilePool(file_group) for file_group in file_groups]

    bind_ip = (const.THIS_IP, use.get_free_port())
    hand_shake = DataWeaver(header=const.CMD_RECV_FILE,
                            content={'count': len(file_pools), 'bind_ip': bind_ip},
                            _id=const.THIS_OBJECT.id)

    if not hand_shake.send(receiver_sock):
        return
    print("sent handshake", hand_shake)  # debug
    sockets = make_sock_groups(len(file_pools), bind_ip=bind_ip)
    print("made connections")  # debug
    print(sockets)  # debug
    print(file_pools)  # debug
    th_pool = ThreadPoolExecutor(max_workers=len(sockets))
    for file, sock in zip(file_pools, sockets):
        print("inside $%%$%^%^&&*", file, sock, type(file), type(sock), type(receiver_id))  # debug
        global_files.add_to_current(receiver_id, file)
        # th_pool.submit(_sock_thread, receiver_id, file, sock)
        threading.Thread(target=_sock_thread, args=(receiver_id, file, sock)).start()

    th_pool.shutdown()  # wait for all threads to finish  # debug
    print("completed mapping threads")  # debug


def fileReceiver(file_data: DataWeaver):
    print("inside fileRecv")  # debug
    conn_count = file_data.content['count']
    sender_id = file_data.id
    if not conn_count:
        return
    print(f"{conn_count=}")  # debug

    # print("got to recv ", file_data)  # debug

    def _sock_thread(_id, _file: FiLe, _conn):
        # print("inside recv_files parent :",_file, _conn)  # debug
        with _conn:
            if _file.recv_files(_conn):
                global_files.add_to_completed(_id, _file)
            else:
                global_files.add_to_continued(_id, _file)

        print("Done :", _file)  # debug

    file_pools = [PeerFilePool() for _ in range(conn_count)]
    sockets = make_sock_groups(conn_count, connect_ip=tuple(file_data.content['bind_ip']))
    print(sockets)  # debug

    print(file_pools)
    th_pool = ThreadPoolExecutor(max_workers=conn_count)
    for file, sock in zip(file_pools, sockets):
        global_files.add_to_current(sender_id, file)
        # th_pool.submit(_sock_thread, sender_id, file, sock)
        threading.Thread(target=_sock_thread, args=(sender_id, file, sock)).start()
    th_pool.shutdown()  # wait for all threads to finish  # debug
    print(f"{file_pools=}")  # debug
    print("completed mapping threads")  # debug


def open_file_dialog_window(prev_directory=[None, ]):  # this param is use as a cache for recent directory
    """Opens the system-like file picker dialog.
    :type prev_directory: list
    """
    _ = QApplication([])
    dialog = QFileDialog()
    dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    dialog.setWindowFlags(Qt.WindowStaysOnTopHint | dialog.windowFlags())

    files = dialog.getOpenFileNames(directory=prev_directory[0],
                                        caption="Select files to send")[0]
    prev_directory[0] = os.path.dirname(files[0])
    return files


def endFileThreads():
    try:
        for file_list in global_files.current:
            for file in file_list:
                file.break_loop()
    except AttributeError as e:
        error_log(f"::Error at endFileThreads() from  endFileThreads/filemanager at line 79: {e}")
    return True


# deprecated methods of sending files
from src.avails.fileobject import _PeerFile  # _PeerFile is now deprecated


@NotInUse
def __setFileId(file: tuple[FiLe], receiver_obj: RemotePeer):
    global every_file
    receiver_obj.increment_file_count()
    every_file[f"{receiver_obj.id}(^){receiver_obj.get_file_count()}"] = file


@NotInUse
def _fileSender(_data: DataWeaver, receiver_sock, is_dir=False):
    receiver_obj, prompt_data = RemotePeer(), ''
    if _data.content == "":
        files_list = open_file_dialog_window()
        for file in files_list:
            _data.content = file
            _fileSender(_data, receiver_sock, is_dir)
    try:
        receiver_obj: RemotePeer = peer_list.get_peer(_data.id)
        temp_port = use.get_free_port()

        file = _PeerFile(uri=(const.THIS_IP, temp_port), path=_data.content)
        __setFileId(file, receiver_obj)

        _header = (const.CMD_RECV_DIR if is_dir else const.CMD_RECV_FILE)
        _id = json.dumps([const.THIS_IP, temp_port])

        try:
            DataWeaver(header=_header, content=file.get_meta_data(), _id=_id).send(receiver_sock)
        except socket.error:
            pass  # give feed back that can't send file, ask for feedback

        if file.verify_handshake():
            file.send_file()
            print("::file sent: ", file.filename, " to ", receiver_sock.getpeername())
            prompt_data = DataWeaver(header="this is a prompt", content=file.filename, _id=receiver_obj.id)
            return file.filename
        return False

    except NotADirectoryError as nde:
        prompt_data = DataWeaver(header="this is a prompt", content=nde.filename, _id=receiver_obj.id)
    except FileNotFoundError as fne:
        prompt_data = DataWeaver(header="this is a prompt", content=fne.filename, _id=receiver_obj.id)
    finally:
        # asyncio.run(handle_data_flow.feed_core_data_to_page(prompt_data))
        pass


@NotInUse
def _fileReceiver(refer: DataWeaver):
    recv_ip, recv_port = json.loads(refer.id)
    file = _PeerFile(uri=(recv_ip, recv_port))
    metadata = refer.content
    file.set_meta_data(filename=metadata['name'], file_size=int(metadata['size']))

    if file.recv_handshake():
        file.recv_file()

    return file.filename
