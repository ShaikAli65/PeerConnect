from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from os import PathLike
import tqdm
from multiprocessing import Process

from src.core import *
from src.avails.remotepeer import RemotePeer
from src.avails import useables as use
from src.avails.fileobject import PeerFile
from src.webpage import handle_data
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
        directorySender(_data, receiver_sock)
    except FileNotFoundError as fne:
        prompt_data = DataWeaver(header="thisisaprompt", content=fne.filename, _id=receiver_obj.id)
    finally:
        asyncio.run(handle_data.feed_core_data_to_page(prompt_data))
        pass


def fileReceiver(refer: DataWeaver):

    tup = refer.id.split('(^)')
    ip,port = tup[0], int(tup[1])
    file = PeerFile(uri=(ip,port))
    metadata = json.loads(refer.content.strip())
    file.set_meta_data(filename=metadata['name'], file_size=int(metadata['size']))
    if file.recv_meta_data():
        file.recv_file()
    return file.filename


def zipDir(zip_name: str, source_dir: Union[str, PathLike]):
    src_path = Path(source_dir).expanduser().resolve(strict=True)
    with ZipFile(zip_name, 'w', ZIP_DEFLATED) as zf:
        progress = tqdm.tqdm(src_path.rglob('*'), desc="Zipping ", unit=" files")
        for file in src_path.rglob('*'):
            zf.write(file, file.relative_to(src_path.parent))
            progress.update(1)
        progress.close()
    return


def unZipper(zip_path: str, destination_path: str):
    with ZipFile(zip_path, 'r') as zip_ref:
        try:
            zip_ref.extractall(destination_path)
        except PermissionError as pe:
            error_log(f"::PermissionError in unzipper() from core/nomad at line 68: {pe}")
    print(f"::Extracted {zip_path} to {destination_path}")
    os.remove(zip_path)
    return


def directorySender(_data: str, recv_sock:socket.socket):
    receiver_obj: RemotePeer = use.get_peer_obj_from_sock(recv_sock)
    provisional_name = f"temp{receiver_obj.get_file_count()}!!{receiver_obj.id}.zip"
    receiver_obj.increment_file_count()

    zipper_process = Process(target=zipDir, args=(provisional_name, _data))
    zipper_process.start()
    zipper_process.join()

    fileSender(provisional_name, recv_sock, is_dir=True)
    use.echo_print(False, "sent zip file: ", provisional_name)
    os.remove(provisional_name)
    pass


def directoryReceiver(refer: DataWeaver):
    tup = refer.id.split('(^)')
    ip,port = tup[0], int(tup[1])

    file = PeerFile(uri=(ip,port))
    metadata = json.loads(refer.content)
    file.set_meta_data(filename=metadata['name'], file_size=int(metadata['size']))
    if file.recv_meta_data():
        file.recv_file()

    file_unzip_path = os.path.join(const.PATH_DOWNLOAD, file.filename)

    unzip_process = Process(target=unZipper, args=(file_unzip_path, const.PATH_DOWNLOAD))
    unzip_process.start()
    unzip_process.join()

    return file.filename


def endFileThreads():
    global every_file
    for file in every_file.values():
        file.hold()
    every_file.clear()
    return True


def pop_dir_selector_and_send(to_user_obj: RemotePeer):
    dir_path = use.open_directory_dialog_window()
    pass
    return None


def pop_file_selector_and_send(to_user_obj: RemotePeer):
    file_path = use.open_file_dialog_window()
    pass
    return None
