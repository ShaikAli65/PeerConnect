import select

from core import *
from logs import *
from webpage import handle
from core import managerequests as manage_requests


class Nomad:
    currently_in_connection = {}
    LOOP_FLAG = True

    def __init__(self, ip='localhost', port=8088):
        print("::Initiating Nomad Object", ip, port)
        self.address = (ip, port)
        self.safe_stop = True
        const.REMOTE_OBJECT = RemotePeer(const.USERNAME, ip, port, report=const.REQ_PORT, status=1)
        self.peer_sock = socket.socket(const.IP_VERSION, const.PROTOCOL)
        self.peer_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.peer_sock.bind(self.address)

    def commence(self):
        const.HANDLE_CALL.wait()
        print("::Listening for connections at ", self.address)
        self.peer_sock.listen()
        while self.safe_stop:
            if not isinstance(self.peer_sock, socket.socket):
                continue
            readable, _, _ = select.select([self.peer_sock], [], [], 0.001)
            if self.peer_sock not in readable:
                continue
            try:
                initiate_conn, _ = self.peer_sock.accept()
                activitylog(f'New connection from {_[0]}:{_[1]}')
                print(f"New connection from {_[0]}:{_[1]}")
                Nomad.currently_in_connection[initiate_conn] = True
                Nomad.start_thread(connectNew, args=(initiate_conn,))
            except (socket.error, OSError) as e:
                errorlog(f"Socket error: {e}")

        return

    @staticmethod
    def start_thread(_target, args=()):
        if len(args) != 0:
            thread_recv = threading.Thread(target=_target, args=args)
        else:
            thread_recv = threading.Thread(target=_target, daemon=True)
        thread_recv.start()
        return thread_recv

    def end(self):
        self.safe_stop = False
        manage_requests.notify_users()  # notify users that this user is going offline
        if Nomad:
            Nomad.currently_in_connection = dict.fromkeys(Nomad.currently_in_connection, False)
        time.sleep(1)
        self.peer_sock.close() if self.peer_sock else None
        print("::Nomad Object Ended")

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'

    def __del__(self):
        self.end()


@NotInUse
def notify_users():
    const.WEB_SOCKET.send('thisisacommand_/!_sendlistofactivepeers')
    _data = json.loads(const.WEB_SOCKET.recv())
    pass


def send(_to_user_soc, _data: str, _file_status=False):
    if _file_status:
        file = PeerFile(path=_data, obj=_to_user_soc)
        if file.send_meta_data():
            return file.send_file()
        return False

    for _ in range(const.MAX_CALL_BACKS):

        try:
            status = PeerText(_to_user_soc, _data).send()
            return status
        except socket.error as err:
            time.sleep(3)
            if err.errno == 10054:
                return False
            errorlog(f"Error in sending data: {e}")
            print(f"Error in sending data retrying... {err}")
            continue

    return False


def recv_file(_conn: socket.socket):
    Nomad.currently_in_connection[_conn] = True
    if not _conn:
        print("::Closing connection from recv_file() from core/nomad at line 100")
        return
    getdata_file = PeerFile(recv_soc=_conn)
    st = getdata_file.recv_meta_data()

    if st:
        getdata_file.recv_file()
    return


def connectNew(_conn: socket.socket):
    recv_sock_lock = threading.Lock()
    while Nomad.currently_in_connection[_conn]:
        readable, _, _ = select.select([_conn], [], [], 0.001)
        if _conn not in readable:
            continue
        with recv_sock_lock:
            connectNew_data = PeerText(_conn)
            connectNew_data.receive()
        print('data from peer :', connectNew_data)
        if connectNew_data.raw_text == const.CMD_CLOSING_HEADER:
            disconnect_user(_conn)
            return True
        elif connectNew_data.raw_text == const.CMD_RECV_FILE:
            # asyncio.run(handle.feed_user_data(_conn, recvdata_sock_lock))
            threading.Thread(target=recv_file,args=(_conn,)).start()
        elif connectNew_data.raw_text:
            asyncio.run(handle.feed_user_data(connectNew_data, _conn.getpeername()))
        time.sleep(1)

    return True


def disconnect_user(_conn):
    _conn.close()
    print("::Closing connection from disconnect_user() from core/nomad at line 153")
