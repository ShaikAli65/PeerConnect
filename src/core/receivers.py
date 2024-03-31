import src.managers.directorymanager
from src.core import *
import src.avails.useables as use
from src.webpage_handlers import handle_data
from src.managers import *
from src.avails.textobject import DataWeaver


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
            use.echo_print(False, f"::Connection error: at {connectNew.__name__}()/{os.path.relpath(connectNew.__code__.co_filename)} exp:{e}", _conn.getpeername())
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


def disconnectUser(_conn, currently_in_connection):
    currently_in_connection[_conn] = False
    with _conn:
        DataWeaver(header=const.CMD_CLOSING_HEADER).send(_conn)
    _conn.close()
    use.echo_print(False, f"::Closing connection from {disconnectUser.__name__}()/{os.path.relpath(disconnectUser.__code__.co_filename)}")
