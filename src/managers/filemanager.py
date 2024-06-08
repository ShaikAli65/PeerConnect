# This file is responsible for sending and receiving files between peers.
import importlib
import select

from concurrent.futures import ThreadPoolExecutor

from src.avails.container import FileDict
from src.avails.dialogs import Dialog
from src.core import *
from src.avails.remotepeer import RemotePeer
from src.avails import useables as use
from src.avails.textobject import DataWeaver
from src.avails.fileobject import FiLe, make_file_groups, make_sock_groups, PeerFilePool
from src.webpage_handlers.handle_data import feed_file_data_to_page

global_files = FileDict()


def fileSender(file_data: DataWeaver, receiver_sock):
    file_list = file_data.content['files']
    receiver_id = file_data.id
    if file_list == ['']:
        file_list = Dialog.open_file_dialog_window()
    if not file_list:
        return
    receiver_obj = peer_list.get_peer(receiver_id)

    def _sock_thread(_id, _file: FiLe, conn):
        with conn:
            conn.send(struct.pack('!I', _file.id))
            if _file.send_files(conn):
                global_files.add_to_completed(_id, _file)
            else:
                global_files.add_to_continued(_id, _file)
                use.echo_print("ERROR ERROR SOMETHING WRONG IN SENDING FILES")

    file_groups = make_file_groups(file_list, grouping_level=file_data.content['grouping_level'])
    # file_groups = make_file_groups(file_list, grouping_level=4)
    file_pools = [PeerFilePool(file_group, _id=receiver_obj.get_file_count()) for file_group in file_groups]
    bind_ip = (const.THIS_IP, use.get_free_port())

    send_handshake(1, {'count': len(file_pools), 'bind_ip': bind_ip}, receiver_obj, receiver_sock)

    sockets = make_sock_groups(len(file_pools), bind_ip=bind_ip)
    th_pool = ThreadPoolExecutor(max_workers=len(sockets))
    print("made connections")  # debug
    print(sockets)  # debug

    for file, sock in zip(file_pools, sockets):
        asyncio.run(feed_file_data_to_page({'file_id': file.id}, receiver_id))
        global_files.add_to_current(receiver_id, file)
        # th_pool.submit(_sock_thread, receiver_id, file, sock)
        threading.Thread(target=_sock_thread, args=(receiver_id, file, sock)).start()
    #     print("completed mapping threads")  # debug


def send_handshake(header, content, receiver_obj, receiver_sock):
    try:
        header = const.CMD_RECV_FILE if header == 1 else const.CMD_RECV_FILE_AGAIN
        hand_shake = DataWeaver(header=header, content=content, _id=const.THIS_OBJECT.id)
        hand_shake.send(receiver_sock)
    except (ConnectionResetError, socket.error):
        # retry connecting to peer if this fails then we can return that receiver can't be reached
        connections = getattr(importlib.import_module('src.core.senders'), 'RecentConnections')
        receiver_sock = connections.add_connection(receiver_obj)
        hand_shake = DataWeaver(header=const.CMD_RECV_FILE, content=content, _id=const.THIS_OBJECT.id)
        hand_shake.send(receiver_sock)


def file_receiver(file_data: DataWeaver):
    conn_count = file_data.content['count']
    if not conn_count:
        return
    sender_id = file_data.id

    def _sock_thread(_id, _file: FiLe, conn):
        try:
            # print("inside rec v_files parent :",_file, _conn)  # debug
            with conn:
                _file.id = struct.unpack('!I', conn.recv(4))[0]
                if _file.recv_files(conn):
                    global_files.add_to_completed(_id, _file)
                else:
                    global_files.add_to_continued(_id, _file)
                    use.echo_print("ERROR ERROR SOMETHING WRONG IN RECEIVING FILES")
        finally:
            print("Done :", _file)  # debug

    file_pools = [PeerFilePool(_id=0) for _ in range(conn_count)]
    sockets = make_sock_groups(conn_count, connect_ip=tuple(file_data.content['bind_ip']))
    print(sockets)  # debug

    print(file_pools)  # debug

    th_pool = ThreadPoolExecutor(max_workers=conn_count)
    for file, sock in zip(file_pools, sockets):
        global_files.add_to_current(sender_id, file)
        # th_pool.submit(_sock_thread, sender_id, file, sock)
        threading.Thread(target=_sock_thread, args=(sender_id, file, sock)).start()
#     th_pool.shutdown()  # wait for all threads to finish  # debug
#     print("completed mapping threads")  # debug
#     print('\n'.join(str(x) for x in file_pools))  # debug


def stop_a_file(refer_data: DataWeaver):
    peer_id = refer_data.id
    file_id = refer_data.content['file_id']
    file_pool = global_files.get_running_file(peer_id, file_id).break_loop()
    global_files.add_to_continued(peer_id, file_pool)


def resend_file(refer_data: DataWeaver, receiver_sock):
    peer_id = refer_data.id
    file_id = refer_data.content['file_id']
    file_pool: PeerFilePool = global_files.get_continued_file(peer_id, file_id)
    bind_ip = (const.THIS_IP,use.get_free_port())

    send_handshake(2,{'bind_ip':bind_ip,'file_id':file_id}, peer_list.get_peer(peer_id), receiver_sock)

    with socket.create_server(bind_ip, backlog=1) as soc:
        reads,_,_ = select.select([file_pool.__controller, soc],[],[],50)
        if soc in reads:
            receiver_conn, _ = soc.accept()
        else:
            return

    if file_pool.send_files_again(receiver_conn):
        global_files.add_to_completed(peer_id, file_pool)


def re_receive_file(refer_data: DataWeaver):
    peer_id = refer_data.id
    file_id = refer_data.content['file_id']
    file_pool: PeerFilePool = global_files.get_continued_file(peer_id, file_id)
    addr = refer_data.content['bind_ip']
    with socket.create_connection((addr[0], addr[1]), timeout=20) as conn_sock:
        if file_pool.receive_files_again(conn_sock):
            global_files.add_to_completed(peer_id, file_pool)


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
        files_list = Dialog.open_file_dialog_window()
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
