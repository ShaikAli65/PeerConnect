import json

import select
from core import *
from core.fileobject import PeerFile
from core.remotepeer import RemotePeer
from logs import *
from webpage import handle


async def notify_users():
    const.WEBSOCKET.send('thisisacommand_/!_sendlistofactivepeers')
    _data = json.loads(const.WEBSOCKET.recv())
    pass


class Nomad:
    currently_in_connection = {}

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

    def send(self, _touser, _data, filestatus=False):
        if filestatus:
            self.send_file(_touser, _data)
        if _data:
            _data = _data.encode(const.FORMAT)
            _datalen = struct.pack('!I', len(_data))
            for _ in range(const.MAXCALLBACKS):

                try:
                    with self.peersock as sock:
                        readables, _, _ = select.select([sock], [], [], 0.001)
                        if sock not in readables:
                            continue
                        sock.connect(_touser)
                        sock.sendall(_datalen)
                        sock.sendall(_data)
                        sock.close()
                    return True
                except Exception as e:
                    time.sleep(1)
                    # errorlog(f"Error in sending data: {e}")
                    print(f"Error in sending data retrying... {e}")
                    continue

        return

    def send_file(self, ip: str, filedata: str):
        with self.peersock as sock:
            sock.connect(ip)
            sendfile_cmd = const.CMDSENDFILE.encode(const.FORMAT)
            sock.sendall(struct.pack('!I', len(sendfile_cmd)))
            sock.sendall(sendfile_cmd)
            time.sleep(0.2)
            file = PeerFile(path=filedata, sock=sock)
            file.send_meta_data()
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


def recv_file(_conn: socket.socket):
    Nomad.currently_in_connection[_conn] = True

    getdata_file = PeerFile(sock=_conn)
    getdata_file.recv_meta_data()
    getdata_file.recv_file()
    return


def recv_data(_conn: socket.socket):
    c = 0
    recvdata_flag = True
    while recvdata_flag:

        try:
            readables, _, _ = select.select([_conn], [], [], 0.001)
            if _conn not in readables:
                continue
            recvdata_raw_len = _conn.recv(4)
            get_datalen = struct.unpack('!I',recvdata_raw_len)[0] if recvdata_raw_len else 0
            if get_datalen == 0:
                continue
            recvdata_data = _conn.recv(get_datalen)
            print(f"data from {_conn.getpeername()} :", recvdata_data)  # debug
            if recvdata_data.decode(const.FORMAT) == const.CMDRECVFILE:
                time.sleep(0.1)
                Nomad.start_thread(recv_file, args=(_conn,))
                return True
            elif recvdata_data == const.CMDCLOSINGHEADER:
                _conn.close()
                recvdata_flag = False
            elif recvdata_data:
                asyncio.run(handle.feeduserdata(recvdata_data, _conn.getpeername()))
        except Exception as e:
            errorlog(f"Error at recv_data() from core/nomad at line 140 :{e}")
            _conn.sendall(struct.pack('!I', len(const.CMDCLOSINGHEADER)))
            _conn.sendall(const.CMDCLOSINGHEADER)
            _conn.close()
            return False

    return True
