import src.managers.directorymanager
from src.core import *
import src.avails.useables as use
from src.core import handle_data
from src.managers import *
from src.avails.textobject import DataWeaver

function_map = {
    # const.CMD_CLOSING_HEADER: lambda connection_socket: disconnectUser(connection_socket),
    const.CMD_RECV_DIR: lambda connection_socket: "sent you a dir : " + src.managers.directorymanager.directoryReceiver(connection_socket),
    const.CMD_RECV_FILE: lambda connection_socket: "sent you a file : " + filemanager.fileReceiver(connection_socket),
    # const.CMD_RECV_DIR_LITE: lambda connection_socket: "sent you a directory through lite : " + directorymanager.directory_receiver(connection_socket),
    const.CMD_TEXT:lambda data: data
}


def connectNew(_conn: socket.socket, currently_in_connection):
    while currently_in_connection.get(_conn):
        readable, _, _ = select.select([_conn], [], [], 592)
        if _conn not in readable:
            use.echo_print(False, f"::Connection timed out : at {connectNew.__name__}()/{os.path.relpath(connectNew.__code__.co_filename)}", _conn.getpeername())
            disconnectUser(_conn, currently_in_connection)
            return
        try:
            if _conn.recv(1, socket.MSG_PEEK) == b'':
                return
            _data = DataWeaver().receive(_conn)
        except socket.error as e:
            use.echo_print(False, f"::Connection error: at {__name__}/{__file__} exp:{e}", _conn.getpeername())
            return
        use.echo_print(False, 'data from peer :', _data)

        if _data.header == const.CMD_TEXT:
            asyncio.run(handle_data.feed_user_data_to_page(_data.content, _data.id))
            continue

        elif _data.header == const.CMD_RECV_FILE:
            use.start_thread(_target=filemanager.fileReceiver, _args=(_data,))

        elif _data.header == const.CMD_RECV_DIR:
            src.managers.directorymanager.directoryReceiver(refer=_data)

        elif _data.header == const.CMD_CLOSING_HEADER:
            disconnectUser(_conn, currently_in_connection)

    disconnectUser(_conn, currently_in_connection)
    return


def handle_data_flow(_data: DataWeaver, _conn: socket.socket):
    if _data.header == const.CMD_TEXT:
        asyncio.run(handle_data.feed_user_data_to_page(_data.content, _data.id))
    elif _data.header in function_map:
        function_map[_data.header](_conn)


def disconnectUser(_conn, currently_in_connection):
    currently_in_connection[_conn] = False
    with _conn:
        DataWeaver(header=const.CMD_CLOSING_HEADER).send(_conn)
    _conn.close()
    use.echo_print(False, f"::Closing connection from {disconnectUser.__name__}()/{os.path.relpath(disconnectUser.__code__.co_filename)}")
