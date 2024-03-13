from src.core import *
from src.avails.remotepeer import RemotePeer
from src.avails import useables as use
from src.avails.fileobject import PeerFile
from src.avails.textobject import DataWeaver


every_file = {}
count = 0


def __setFileId(file: PeerFile, receiver_obj: RemotePeer):
    global every_file
    receiver_obj.increment_file_count()
    every_file[f"{receiver_obj.id}(^){receiver_obj.get_file_count()}"] = file


def fileSender(_data: str, receiver_sock: socket.socket, is_dir=False):
    receiver_obj,prompt_data = RemotePeer(), ''
    try:
        receiver_obj: RemotePeer = use.get_peer_obj_from_sock(_conn=receiver_sock)
        temp_port = use.get_free_port()
        file = PeerFile(uri=(const.THIS_IP, temp_port), path=_data)
        __setFileId(file, receiver_obj)
        _header = (const.CMD_RECV_DIR if is_dir else const.CMD_RECV_FILE)
        _id = f"{const.THIS_IP}(^){temp_port}"
        DataWeaver(header=_header,content=file.get_meta_data(),_id=_id).send(receiver_sock)
        time.sleep(0.07)
        if file.send_meta_data():
            file.send_file()
            print("::file sent: ", file.filename, " to ", receiver_sock.getpeername())
            prompt_data = DataWeaver(header="thisisaprompt", content=file.filename, _id=receiver_obj.id)
            return file.filename
        return False
    except NotADirectoryError as nde:
        prompt_data = DataWeaver(header="thisisaprompt", content=nde.filename, _id=receiver_obj.id)
    except FileNotFoundError as fne:
        prompt_data = DataWeaver(header="thisisaprompt", content=fne.filename, _id=receiver_obj.id)
    finally:
        # asyncio.run(handle_data.feed_core_data_to_page(prompt_data))
        pass


def fileReceiver(refer: DataWeaver):
    tup = refer.id.split('(^)')
    file = PeerFile(uri=(tup[0], int(tup[1])))

    metadata = json.loads(refer.content.strip())
    file.set_meta_data(filename=metadata['name'], file_size=int(metadata['size']))

    if file.recv_meta_data():
        file.recv_file()

    return file.filename


def endFileThreads():
    global every_file
    try:
        for file in every_file.values():
            file.hold()
    except AttributeError as e:
        error_log(f"::Error at endFileThreads() from  endFileThreads/filemanager at line 79: {e}")
    every_file.clear()
    return True


def pop_dir_selector_and_send(to_user_obj: RemotePeer):
    dir_path = use.open_directory_dialog_window()
    pass
    return None


def pop_file_selector_and_send(connected_socket: socket.socket):
    file_path = use.open_file_dialog_window()
    fileSender(file_path, connected_socket)
    return None
