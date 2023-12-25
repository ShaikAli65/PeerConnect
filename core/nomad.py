import json
import pickle
import socket

import select
from core import *
from core.fileobject import PeerFile
from core.remotepeer import RemotePeer
from core.textobject import PeerText
from logs import *
from webpage import handle


async def notify_users():
    const.WEBSOCKET.send('thisisacommand_/!_sendlistofactivepeers')
    _data = json.loads(const.WEBSOCKET.recv())
    pass


class Nomad:
    currently_in_connection = {}
    LOOPFLAG = True

    def __init__(self, ip='localhost', port=8088):
        print("::Initiating Nomad Object", ip, port)
        self.address = (ip, port)
        self.safestop = True
        const.REMOTEOBJECT = RemotePeer(const.USERNAME, self.address)
        self.peersock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.peersock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.peersock.bind(self.address)

    def initiate(self):
        const.HANDLECALL.wait()
        print("::Listening for connections at ", self.address)
        self.peersock.listen()
        while self.safestop:
            readables, _, _ = select.select([self.peersock], [], [], 0.001)
            if self.peersock in readables:
                try:
                    initiate_conn, _ = self.peersock.accept()
                    activitylog(f"New connection from {_[0]}:{_[1]}")
                    Nomad.currently_in_connection[initiate_conn] = True
                    Nomad.start_thread(recv_data, args=(initiate_conn,))
                except (socket.error, OSError) as e:
                    errorlog(f"Socket error: {e}")
        return

    def send(self, _touser:tuple[str,int], _data:str, filestatus=False):
        if filestatus:
            self.send_file(_touser, _data)
        for _ in range(const.MAXCALLBACKS):

            try:
                send_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                send_sock.connect(_touser)
                readables, _, _ = select.select([send_sock], [], [], 0.001)
                if send_sock not in readables:
                    continue
                with send_sock:
                    send_text = PeerText(send_sock, _data)
                    return send_text.send()
            except Exception as e:
                time.sleep(1)
                # errorlog(f"Error in sending data: {e}")
                print(f"Error in sending data retrying... {e}")
                continue

        return False

    def send_file(self, ip: tuple[str,int], filedata: str):
        with self.peersock as sock:
            sock.connect(ip)
            PeerText(sock, const.CMDRECVFILE).send()
            file = PeerFile(path=filedata, sock=sock)
            if file.send_meta_data():
                file.send_file()
            sock.close()
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
        time.sleep(1)
        self.peersock.close()
        print("::Ending Nomad Object")


def recv_file(_conn: socket.socket, _lock: threading.Lock):
    Nomad.currently_in_connection[_conn] = True
    if not _conn:
        print("::Closing connection from recv_file() from core/nomad at line 100")
        return
    getdata_file = PeerFile(sock=_conn)
    if getdata_file.recv_meta_data(_lock):
        getdata_file.recv_file()
    return


def recv_data(_conn: socket.socket):
    recv_timeout = 0
    recvdata_file_sock_lock = threading.Lock()
    while Nomad.LOOPFLAG:
        if recv_timeout >= 100:
            print("::Closing connection from recv_data() from core/nomad at line 112")
            _conn.close()
            return False

        try:
            readables, _, _ = select.select([_conn], [], [], 0.001)
            if _conn not in readables:
                continue
            with recvdata_file_sock_lock:
                recvdata_data = PeerText(_conn).receive()
            if not recvdata_data:
                continue
            print('data from peer :',_conn.getpeername(), recvdata_data)
            if recvdata_data.decode(const.FORMAT) == const.CMDCLOSINGHEADER:
                _conn.close()
                print("::Closing connection from recv_data() from core/nomad at line 124")
                return True
            elif recvdata_data.decode(const.FORMAT) == const.CMDRECVFILE:
                Nomad.start_thread(recv_file, args=(_conn,recvdata_file_sock_lock))
                time.sleep(3)

            elif recvdata_data:
                asyncio.run(handle.feeduserdata(recvdata_data, _conn.getpeername()))
            else:
                time.sleep(0.5)
                recv_timeout += 1
        except Exception as e:
            errorlog(f"Error at recv_data() from core/nomad at line 140 :{e}")
            try:
                PeerText(_conn, const.CMDCLOSINGHEADER).send() if _conn else None
                _conn.close()
            except socket.error as e:
                errorlog(f"Error at recv_data() in handling closing of client from core/nomad at line 144 :{e}")
            return False

    return True
