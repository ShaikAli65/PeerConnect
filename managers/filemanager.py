from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from os import PathLike
import tqdm

from core import *
import core.nomad as nomad
from avails import dataweaver
from webpage import handle
from avails import remotepeer as remote_peer
from avails import useables as use
from avails.fileobject import PeerFile
every_file = {}
count = 0


def file_sender(receiver_obj: remote_peer.RemotePeer, _data: str, isdir=False):
    prompt_data, file = None, None
    try:
        file = PeerFile(path=_data, obj=receiver_obj, is_dir=isdir)
        receiver_obj.increment_file_count()
        every_file[f"{receiver_obj.id }(^){receiver_obj.get_file_count()}"] = file
        if file.send_meta_data():
            file.send_file()
            prompt_data = dataweaver.DataWeaver(header="thisisaprompt", content=file.filename, _id=receiver_obj.id)
            return file.filename
        return False
    except NotADirectoryError as nde:
        prompt_data = dataweaver.DataWeaver(header="thisisaprompt", content=nde.filename, _id=receiver_obj.id)
        directory_sender(receiver_obj, _data)
    except FileNotFoundError as fne:
        prompt_data = dataweaver.DataWeaver(header="thisisaprompt", content=fne.filename, _id=receiver_obj.id)
    finally:
        asyncio.run(handle.feed_core_data_to_page(prompt_data))


def directory_sender(receiver_obj: remote_peer.RemotePeer, _data: str):
    def zip_dir(zip_name: str, source_dir: Union[str, PathLike]):
        src_path = Path(source_dir).expanduser().resolve(strict=True)
        with ZipFile(zip_name, 'w', ZIP_DEFLATED) as zf:
            progress = tqdm.tqdm(src_path.rglob('*'), desc="Zipping ", unit=" files")
            for file in src_path.rglob('*'):
                zf.write(file, file.relative_to(src_path.parent))
                progress.update(1)
            progress.close()
        return
    provisional_name = f"temp{receiver_obj.get_file_count()}!!{receiver_obj.id}.zip"
    zip_dir(provisional_name, _data)
    print("generated zip file: ", provisional_name)
    file_sender(receiver_obj, provisional_name, isdir=True)
    print("sent zip file: ", provisional_name)
    os.remove(provisional_name)
    pass


def directory_reciever(_conn: socket.socket):
    nomad.Nomad.currently_in_connection[_conn] = True
    if not _conn:
        with const.PRINT_LOCK:
            print("::Closing connection from recv_file() from core/nomad at line 100")
        return
    recv_file = PeerFile(recv_soc=_conn)
    if recv_file.recv_meta_data():
        recv_file.recv_file()

    zip_path = str(os.path.join(const.PATH_DOWNLOAD, recv_file.filename))
    with ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(const.PATH_DOWNLOAD)
    print(f"::Extracted {zip_path} to {const.PATH_DOWNLOAD}")
    os.remove(zip_path)
    return recv_file.filename


def file_reciever(_conn: socket.socket):
    nomad.Nomad.currently_in_connection[_conn] = True
    if not _conn:
        with const.PRINT_LOCK:
            print("::Closing connection from recv_file() from core/nomad at line 100")
        return
    getdata_file = PeerFile(recv_soc=_conn)
    if getdata_file.recv_meta_data():
        getdata_file.recv_file()
    return getdata_file.filename


# def compress_file(file_pa):
#     with open(file_pa, 'rb') as file:
#         compressed_data = zipfile.compress(file.read())
#     return compressed_data


def end_file_threads():
    global every_file
    for file in every_file.values():
        file.hold()
    every_file.clear()
    return True


def pop_dir_selector_and_send(to_user_obj: remote_peer.RemotePeer):
    dir_path = use.open_directory_dialog_window()
    send_file = PeerFile(path=dir_path, obj=to_user_obj)
    if send_file.send_meta_data():
        send_file.send_file()
    return None


def pop_file_selector_and_send(to_user_obj: remote_peer.RemotePeer):
    file_path = use.open_file_dialog_window()
    send_file = PeerFile(path=file_path, obj=to_user_obj)
    if send_file.send_meta_data():
        send_file.send_file()
    return None
