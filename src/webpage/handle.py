import webbrowser
import websockets
import configparser
from collections import deque

from src.webpage import httphandler
import src.avails.textobject
import src.managers.endmanager
from src.core import *
import src.core.nomad as nomad
from src.avails import remotepeer
from src.avails import useables as use
from src.avails.dataweaver import DataWeaver as datawrap
from src.managers import filemanager, directorymanager
from src.core import requests_handler as reqhandler
from src import avails
web_socket: websockets.WebSocketServerProtocol = None
server_data_lock = threading.Lock()
SafeEnd = asyncio.Event()
stack_safe = threading.Lock()
focus_user_stack = deque()


async def send_message(content):
    """
    A Wrapper function to function at {nomad.send()}
    Provides Error Handling And Ensures robustness of sending data.

    :param content:
    :return bool:
    """
    if not len(focus_user_stack):
        return False
    try:
        peer_sock: socket.socket = focus_user_stack[0]
        use.start_thread(_target=nomad.send, _args=(peer_sock, content))
        return True
    except socket.error as exp:
        error_log(f"got error at handle/send_message :{exp}")
        return False


async def send_file(_path):
    """
    :param _path:
    :return bool:
    """
    if not len(focus_user_stack):
        return False
    try:
        peer_remote_sock: socket.socket = focus_user_stack[0]
        with const.LOCK_LIST_PEERS:
            peer_remote_obj = const.LIST_OF_PEERS[peer_remote_sock.getpeername()[0]]
        use.echo_print(False, "at send_file : ", peer_remote_obj, peer_remote_sock.getpeername(), _path)
        use.start_thread(_target=filemanager.file_sender, _args=(peer_remote_obj, _path))
        return True
    except socket.error as exp:
        error_log(f"got error at handle/send_message :{exp}")
        return False


async def send_file_with_window(_path, user_id):
    with const.LOCK_LIST_PEERS:
        peer_remote_obj = const.LIST_OF_PEERS[user_id]
    use.echo_print(False, "at send_file_with_window : ", peer_remote_obj, _path)
    use.start_thread(_target=filemanager.pop_file_selector_and_send, _args=(peer_remote_obj,))
    return


async def send_dir_with_window(_path, user_id):
    with const.LOCK_LIST_PEERS:
        peer_remote_obj = const.LIST_OF_PEERS[user_id]
    use.echo_print(False, "at send_dir_with_window : ", peer_remote_obj, _path)
    use.start_thread(_target=filemanager.pop_dir_selector_and_send, _args=(peer_remote_obj,))
    return


async def handle_connection(addr_id):
    global focus_user_stack
    try:
        with const.LOCK_LIST_PEERS:
            _nomad: avails.remotepeer = const.LIST_OF_PEERS[addr_id]
        conn_socket = socket.socket(const.IP_VERSION, const.PROTOCOL)
        conn_socket.connect(_nomad.uri)
    except KeyError:
        print("Looks like the user is not in the list can't connect to the user")
        return False
    except socket.error as exp:
        error_log(f"got error at handle/handle_connection :{exp}")
        return False
    if _nomad.status == 0:
        return False
    user_conn = focus_user_stack.pop() if len(focus_user_stack) else None
    if user_conn:
        user_conn.close()
    focus_user_stack.append(conn_socket)
    return True


async def command_flow_handler(data_in: datawrap):
    if data_in.match(_content=const.HANDLE_END):
        src.managers.endmanager.end_session()
    elif data_in.match(_content=const.HANDLE_CONNECT_USER):
        await handle_connection(addr_id=data_in.id)
    elif data_in.match(_content=const.HANDLE_POP_DIR_SELECTOR):
        await send_dir_with_window(_path=data_in.content, user_id=data_in.id)
    elif data_in.match(_content=const.HANDLE_PUSH_FILE_SELECTOR):
        await send_file_with_window(_path=data_in.content, user_id=data_in.id)
    elif data_in.match(_content=const.HANDLE_OPEN_FILE):
        use.open_file(data_in.content)
    elif data_in.match(const.HANDLE_RELOAD):
        use.reload_protocol()
        return
    elif data_in.match(const.HANDLE_SYNC_USERS):
        use.start_thread(_target=reqhandler.sync_list)


async def control_data_flow(data_in: datawrap):
    """
    A function to control the data flow from the page
    :param data_in:
    :return:
    """
    function_map = {
        const.HANDLE_COMMAND: lambda x: command_flow_handler(x),
        const.HANDLE_MESSAGE_HEADER: lambda x: send_message(x.content),
        const.HANDLE_FILE_HEADER: lambda x: send_file(x.content),
        const.HANDLE_DIR_HEADER: lambda x: send_file(x.content),
        const.HANDLE_DIR_HEADER_LITE: lambda x: directorymanager.directory_sender(
            receiver_obj=const.LIST_OF_PEERS[x.id], dir_path=x.content),
    }
    try:
        await function_map.get(data_in.header, lambda x: None)(data_in)
    except TypeError as exp:
        error_log(f"Error at handle/control_data_flow : {exp} due to {data_in.header}")


# @NotInUse
async def set_name(new_username):
    config = configparser.ConfigParser()
    config.read(const.PATH_CONFIG)
    config.set('CONFIGURATIONS', 'username', new_username)
    const.USERNAME = new_username


async def getdata():
    global web_socket, SafeEnd
    while not SafeEnd.is_set():
        # try:
        raw_data = await web_socket.recv()
        data = datawrap(byte_data=raw_data)
        with const.LOCK_PRINT:
            print("data from page:", data)
        await control_data_flow(data_in=data)
        # except Exception as e:
        #     print(f"Error in getdata: {e} at handle.py/getdata() ")
        #     break
    print('::SafeEnd is set')


async def handler(_websocket):
    global web_socket, SafeEnd
    web_socket = _websocket
    if const.USERNAME == '':
        userdata = datawrap(header="thisisacommand",
                            content="no..username", )
        await web_socket.send(userdata.dump())
    else:
        userdata = datawrap(header="thisismyusername",
                            content=f"{const.USERNAME}(^){const.THIS_IP}",
                            _id='0')
        await web_socket.send(userdata.dump())
    const.SAFE_LOCK_FOR_PAGE = True
    const.WEB_SOCKET = web_socket
    const.PAGE_HANDLE_CALL.set()
    await getdata()
    use.echo_print(True, '::handler ended')


def initiate_control():
    use.echo_print(True, '::Initiate_control called at handle.py :', const.PATH_PAGE, const.PAGE_PORT)
    # use.start_thread(_target=httphandler.start_serving, _args=())
    # webbrowser.open(f"http://localhost:{const.PAGE_SERVE_PORT}")
    webbrowser.open(os.path.join(const.PATH_PAGE, "index.html"))
    asyncio.set_event_loop(asyncio.new_event_loop())
    start_server = websockets.serve(handler, "localhost", const.PAGE_PORT)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()


async def feed_user_data_to_page(_data: str, ip):
    global web_socket
    _data = datawrap(header="thisismessage",
                     content=f"{_data}",
                     _id=f"{ip}")
    try:
        print(f"::Sending data :{_data} to page: {ip}")
        await web_socket.send(_data.dump())
    except Exception as e:
        error_log(f"Error sending data handle.py/feed_user_data exp: {e}")
        return


async def feed_core_data_to_page(data: datawrap):
    global web_socket
    try:
        print(f"::Sending data :{data} \n to page")
        await web_socket.send(data.dump())
    except Exception as e:
        error_log(f"Error sending data handle.py/feed_core_data exp: {e}")
        return


async def feed_server_data_to_page(peer: avails.remotepeer.RemotePeer):
    global web_socket, server_data_lock
    with server_data_lock:
        _data = datawrap(header=const.HANDLE_COMMAND,
                         content=(peer.username if peer.status else 0),
                         _id=peer.id)
        try:
            with const.LOCK_PRINT:
                print(f"::Sending data :{_data} \nto page: {peer.username}")
            await const.WEB_SOCKET.send(_data.dump())
        except Exception as e:
            error_log(f"Error sending data at handle.py/feed_server_data, exp: {e}")
        pass


def end():
    global SafeEnd, web_socket
    if web_socket is None:
        return None
    SafeEnd.set()
    asyncio.get_event_loop().stop() if asyncio.get_event_loop().is_running() else None
    if asyncio.get_running_loop().is_running():
        asyncio.get_running_loop().stop()
        asyncio.get_running_loop().close()
    use.echo_print(True, "::Handle Ended")
    return
