import os.path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog

from src.core import *
from src.avails.remotepeer import RemotePeer
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.avails.fileobject import FiLe, make_file_groups, make_sock_groups, PeerFile, \
    _PeerFile  # _PeerFile is now deprecated

every_file: Dict[str, Tuple[FiLe]] = {}  # every file sent in the current session are held here for further control


def add_to_list(_id, file_list):
    global every_file
    if every_file.get(str(_id)):
        every_file[str(_id)] += tuple(file_list)
    else:
        every_file[str(_id)] = tuple(file_list)


def __setFileId(file: tuple[FiLe], receiver_obj: RemotePeer):
    global every_file
    receiver_obj.increment_file_count()
    every_file[f"{receiver_obj.id}(^){receiver_obj.get_file_count()}"] = file


def _start_file_sending_threads(file_groups, sockets):
    def sock_thread(_file: FiLe, _conn: socket.socket):
        with _conn:
            _file.send_files(_conn)

    file_list = []
    for file_items, conn in zip(file_groups, sockets):
        file = PeerFile(paths=file_items)
        use.start_thread(_target=sock_thread, _args=(file, conn))
        file_list.append(file)
    return file_list


def fileSender(file_data: DataWeaver, receiver_sock: socket.socket):
    file_list = file_data.content['list'] or open_file_dialog_window()
    if not file_list:
        return
    file_groups = make_file_groups(file_list,grouping_level=file_data.content['grouping_level'])
    # print(file_groups)
    bind_ip = (const.THIS_IP, use.get_free_port())
    hand_shake = DataWeaver(header=const.CMD_RECV_FILE, content={'count': len(file_groups)},
                            _id=bind_ip)

    if not hand_shake.send(receiver_sock):
        return

    sockets = make_sock_groups(len(file_groups), bind_ip=bind_ip)

    file_list_threads = _start_file_sending_threads(file_groups, sockets)
    add_to_list(file_data.id, file_list_threads)


def fileReceiver(file_data: DataWeaver):
    conn_count = file_data.content['count']
    sockets = make_sock_groups(conn_count, connect_ip=tuple(file_data.id))

    def sock_thread(_file: FiLe, _conn: socket.socket):
        with _conn:
            _file.recv_files(_conn)

    file_list = []
    for conn in sockets:
        file = PeerFile()
        use.start_thread(_target=sock_thread, _args=(file, conn))
        file_list.append(file)

    add_to_list(file_data.id, file_list)


def open_file_dialog_window(prev_directory=["", ]) -> list[str]:
    """Opens the system-like file picker dialog.
    :type prev_directory: list
    """
    app = QApplication([])
    dialog = QFileDialog()
    dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    dialog.setWindowFlags(Qt.WindowStaysOnTopHint | dialog.windowFlags())
    files = dialog.getOpenFileNames(directory=prev_directory[0],
                                    caption="Select files to send")[0]
    try:
        prev_directory[0] = os.path.dirname(files[0])
    except IndexError:
        pass
    return files


def endFileThreads():
    global every_file
    try:
        for file in every_file.values():
            file.hold()
    except AttributeError as e:
        error_log(f"::Error at endFileThreads() from  endFileThreads/filemanager at line 79: {e}")
    every_file.clear()
    return True


# deprecated methods of sending files


@NotInUse
def _fileSender(_data: DataWeaver, receiver_sock: socket.socket, is_dir=False):
    receiver_obj, prompt_data = RemotePeer(), ''
    if _data.content == "":
        files_list = open_file_dialog_window()
        for file in files_list:
            _data.content = file
            _fileSender(_data, receiver_sock, is_dir)
    try:
        receiver_obj: RemotePeer = use.get_peer_obj_from_id(_data.id)
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
