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


def fileSender(_data: DataWeaver, receiver_sock: socket.socket, is_dir=False):
    receiver_obj,prompt_data = RemotePeer(), ''
    if _data.content == "":
        files_list = use.open_file_dialog_window()
        for file in files_list:
            _data.content = file
            fileSender(_data, receiver_sock, is_dir)
    try:
        receiver_obj: RemotePeer = use.get_peer_obj_from_id(_data.id)
        temp_port = use.get_free_port()
        file = PeerFile(uri=(const.THIS_IP, temp_port), path=_data.content)
        __setFileId(file, receiver_obj)
        _header = (const.CMD_RECV_DIR if is_dir else const.CMD_RECV_FILE)
        _id = f"{const.THIS_IP}(^){temp_port}"
        try:
            DataWeaver(header=_header,content=file.get_meta_data(),_id=_id).send(receiver_sock)
        except socket.error:
            pass  # give feed back that can't send file, ask for feedback
        if file.verify_handshake():
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
        # asyncio.run(handle_data_flow.feed_core_data_to_page(prompt_data))
        pass


def fileReceiver(refer: DataWeaver):

    recv_ip, recv_port = refer.id.split('(^)')
    file = PeerFile(uri=(recv_ip, int(recv_port)))
    metadata = json.loads(refer.content.strip())
    file.set_meta_data(filename=metadata['name'], file_size=int(metadata['size']))

    if file.recv_handshake():
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
