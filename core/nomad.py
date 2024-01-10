import json
import socket

import select
from core import *
from core.fileobject import PeerFile
from core.remotepeer import RemotePeer
from core.textobject import PeerText
from logs import *
from webpage import handle


class Nomad:
    currently_in_connection = {}
    LOOPFLAG = True

    def __init__(self, ip='localhost', port=8088):
        print("::Initiating Nomad Object", ip, port)
        self.address = (ip, port)
        self.safestop = True
        const.REMOTEOBJECT = RemotePeer(const.USERNAME, ip, port, reqport=const.REQPORT, status=1)
        self.peer_sock = socket.socket(const.IPVERSION, const.PROTOCOL)
        self.peer_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.peer_sock.bind(self.address)

    def commence(self):
        const.HANDLECALL.wait()
        # print("::Listening for connections at ", self.address)
        self.peer_sock.listen()
        while self.safestop:
            if not isinstance(self.peer_sock, socket.socket):
                continue

            readables, _, _ = select.select([self.peer_sock], [], [], 0.001)
            if self.peer_sock in readables:

                try:
                    initiate_conn, _ = self.peer_sock.accept()
                    # activitylog(f"New connection from {_[0]}:{_[1]}")
                    print(f"New connection from {_[0]}:{_[1]}")
                    Nomad.currently_in_connection[initiate_conn] = True
                    Nomad.start_thread(connectNew, args=(initiate_conn,))
                except (socket.error, OSError) as e:
                    errorlog(f"Socket error: {e}")

        return

    @staticmethod
    def start_thread(_target, args=()):
        if len(args) != 0:
            threadrecv = threading.Thread(target=_target, args=args)
        else:
            threadrecv = threading.Thread(target=_target, daemon=True)
        threadrecv.start()
        return threadrecv

    def end(self):
        self.safestop = False
        # asyncio.run(notifyusers())  # notify users that this user is going offline
        Nomad.currently_in_connection = dict.fromkeys(Nomad.currently_in_connection, False)
        time.sleep(1)
        self.peer_sock.close()
        print("::Ending Nomad Object")

    def __repr__(self):
        return f'Nomad({self.address[0]}, {self.address[1]})'

    def __del__(self):
        self.end()


@NotInUse
def notify_users():
    const.WEBSOCKET.send('thisisacommand_/!_sendlistofactivepeers')
    _data = json.loads(const.WEBSOCKET.recv())
    pass


def send(_touser_soc: socket.socket, _data: str, filestatus=False):
    if filestatus:
        file = PeerFile(path=_data, sock=_touser_soc)
        if file.send_meta_data():
            return file.send_file()
        return False

    for _ in range(const.MAXCALLBACKS):

        try:
            status = PeerText(_touser_soc, _data).send()
            return status
        except socket.error as err:
            time.sleep(3)
            if err.errno == 10054:
                return False
            # errorlog(f"Error in sending data: {e}")
            print(f"Error in sending data retrying... {err}")
            continue

    return False


def recv_file(_conn: socket.socket, _lock: threading.Lock):
    Nomad.currently_in_connection[_conn] = True
    if not _conn:
        print("::Closing connection from recv_file() from core/nomad at line 100")
        return
    getdata_file = PeerFile(sock=_conn)
    with _lock:
        st = getdata_file.recv_meta_data()
    if st:
        getdata_file.recv_file()
    return


def connectNew(_conn: socket.socket):
    recvdata_sock_lock = threading.Lock()
    readables, _, _ = select.select([_conn], [], [], 0.001)
    # if _conn not in readables:
    #     continue
    while Nomad.currently_in_connection[_conn] and _conn in readables:

        with recvdata_sock_lock:
            recvdata_data = PeerText(_conn)
            recvdata_data.receive()
        if not recvdata_data.raw_text:
            _conn.close() if _conn else None
            return False
        print('data from peer :', recvdata_data)
        function_map_to_cmd_headers = {
            const.CMDCLOSINGHEADER: lambda: disconnect_user(_conn),
            const.CMDRECVFILE: lambda: recv_file(_conn, recvdata_sock_lock),
            recvdata_data: lambda: asyncio.run(handle.feeduserdata(recvdata_data, _conn.getpeername()))
        }
        function_map_to_cmd_headers.get(recvdata_data, lambda: None)()
        # except Exception as e:
        #     # errorlog(f"Error at connectNew() from core/nomad at line 140 :{e}")
        #     print("line 157", e)
        #     try:
        #         PeerText(_conn, const.CMDCLOSINGHEADER).send() if _conn else None
        #         _conn.close()
        #     except socket.error as e:
        #         errorlog(f"Error at connectNew() in handling closing of client from core/nomad at line 144 :{e}")
        #     return False

    return True


def disconnect_user(_conn):
    _conn.close()
    print("::Closing connection from disconnect_user() from core/nomad at line 153")
