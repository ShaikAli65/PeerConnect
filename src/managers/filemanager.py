# This file is responsible for sending and receiving files between peers.
import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog
from concurrent.futures import ThreadPoolExecutor

from src.avails.container import FileDict
from src.core import *
from src.avails.remotepeer import RemotePeer
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.avails.fileobject import FiLe, make_file_groups, make_sock_groups, PeerFilePool
# from src.trails.test import FiLe, make_file_groups, make_sock_groups, PeerFilePool
from src.webpage_handlers.handle_data import feed_file_data_to_page

global_files = FileDict()


def fileSender(file_data: DataWeaver, receiver_sock):
    file_list = file_data.content['files']
    receiver_id = file_data.id
    if file_list == ['']:
        file_list = open_file_dialog_window()
    if not file_list:
        return
    receiver_obj = peer_list.get_peer(receiver_id)

    def _sock_thread(_id, _file: FiLe, _conn):
        with _conn:
            if _file.send_files(_conn):
                global_files.add_to_completed(_id, _file)
            else:
                global_files.add_to_continued(_id, _file)
                print("ERROR ERROR SOMETHING WRONG IN SENDING FILES")

    # file_groups = make_file_groups(file_list, grouping_level=file_data.content['grouping_level'])
    file_groups = make_file_groups(file_list, grouping_level=2)
    file_pools = [PeerFilePool(file_group, _id=receiver_obj.get_file_count()) for file_group in file_groups]
    bind_ip = (const.THIS_IP, use.get_free_port())
    hand_shake = DataWeaver(header=const.CMD_RECV_FILE,
                            content={'count': len(file_pools), 'bind_ip': bind_ip},
                            _id=const.THIS_OBJECT.id)
    if not hand_shake.send(receiver_sock):
        return
    print("sent handshake", hand_shake)  # debug
    sockets = make_sock_groups(len(file_pools), bind_ip=bind_ip)
    print(file_pools)  # debug
    th_pool = ThreadPoolExecutor(max_workers=len(sockets))
    print("made connections")  # debug
    print(sockets)  # debug
    for file, sock in zip(file_pools, sockets):
        asyncio.run(feed_file_data_to_page({'file_id': file.id}, receiver_id))
        global_files.add_to_current(receiver_id, file)
        # th_pool.submit(_sock_thread, receiver_id, file, sock)
        threading.Thread(target=_sock_thread, args=(receiver_id, file, sock)).start()

    th_pool.shutdown()  # wait for all threads to finish  # debug
    print("completed mapping threads")  # debug


def fileReceiver(file_data: DataWeaver):
    conn_count = file_data.content['count']
    if not conn_count:
        return
    sender_id = file_data.id
    sender_obj: RemotePeer = peer_list.get_peer(sender_id)

    def _sock_thread(_id, _file: FiLe, _conn):
        # print("inside rec v_files parent :",_file, _conn)  # debug
        try:
            with _conn:
                if _file.recv_files(_conn):
                    global_files.add_to_completed(_id, _file)
                else:
                    global_files.add_to_continued(_id, _file)
                    print("ERROR ERROR SOMETHING WRONG IN RECEIVING FILES")
        finally:
            print(_file)
        print("Done :", _file)  # debug

    file_pools = [PeerFilePool(_id=sender_obj.get_file_count()) for _ in range(conn_count)]
    sockets = make_sock_groups(conn_count, connect_ip=tuple(file_data.content['bind_ip']))
    print(sockets)  # debug

    print(file_pools)

    def waiter(_sock):
        time.sleep(1)
        _sock.close()
    # threading.Thread(target=waiter, args=(next(sockets.__iter__()),)).start()
    th_pool = ThreadPoolExecutor(max_workers=conn_count)
    for file, sock in zip(file_pools, sockets):
        global_files.add_to_current(sender_id, file)
        # th_pool.submit(_sock_thread, sender_id, file, sock)
        threading.Thread(target=_sock_thread, args=(sender_id, file, sock)).start()
    th_pool.shutdown()  # wait for all threads to finish  # debug
    print("completed mapping threads")  # debug
    print('\n'.join(str(x) for x in file_pools))  # debug


def stop_a_file(refer_data: DataWeaver):
    peer_id = refer_data.id
    file_id = refer_data.content['file_id']
    file_pool = global_files.get_running_file(peer_id, file_id).break_loop()
    global_files.add_to_continued(peer_id, file_pool)


def resend_file(refer_data: DataWeaver):
    peer_id = refer_data.id
    file_id = refer_data.content['file_id']
    file_pool = global_files.get_continued_file(peer_id, file_id)
    file_pool.resume_loop()


def open_file_dialog_window(_prev_directory=[os.path.join(os.path.expanduser('~'), 'Downloads'), ]):
    """Opens the system-like file picker dialog.
    #:_prev_directory: this param is use as a cache for recent directory
    :type _prev_directory: list
    """
    _ = QApplication([])
    dialog = QFileDialog()
    dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    dialog.setWindowFlags(Qt.WindowStaysOnTopHint | dialog.windowFlags())
    files = dialog.getOpenFileNames(directory=_prev_directory[0],
                                    caption="Select files to send")[0]
    _prev_directory[0] = os.path.dirname(files[0])
    return files


def endFileThreads():
    try:
        for file_list in global_files.current:
            for file in file_list:
                file.break_loop()
    except AttributeError as e:
        error_log(f"::Error at endFileThreads() from  endFileThreads/file manager at line 79: {e}")
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
            # prompt_data = DataWeaver(header="this is a prompt", content=file.filename, _id=receiver_obj.id)
            return file.filename
        return False

    except NotADirectoryError:
        # prompt_data = DataWeaver(header="this is a prompt", content=nde.filename, _id=receiver_obj.id)
        pass
    except FileNotFoundError:
        # prompt_data = DataWeaver(header="this is a prompt", content=fne.filename, _id=receiver_obj.id)
        pass
    finally:
        # asyncio.run(handle_data_flow.feed_core_data_to_page(prompt_data))
        pass


@NotInUse
def _fileReceiver(refer: DataWeaver):
    rec_v_port: object
    rec_v_ip, rec_v_port = json.loads(refer.id)
    file = _PeerFile(uri=(rec_v_ip, rec_v_port))
    metadata = refer.content
    file.set_meta_data(filename=metadata['name'], file_size=int(metadata['size']))

    if file.recv_handshake():
        file.recv_file()

    return file.filename
