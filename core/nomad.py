import asyncio
import select
import json


from webpage import handle
from logs import *
from core import constants as const
from core import *


async def notify_users():
    const.WEBSOCKET.send('thisisacommand_/!_sendlistofactivepeers')
    _data = json.loads(const.WEBSOCKET.recv())
    pass


class Nomad:
    currently_in_connection = {}

    class peer:
        def __init__(self, username: str, uri: tuple[str, int]):
            self.username = username
            self.uri = uri

        def __str__(self):
            return f'{self.username}~^~{self.uri[0]}~^~{self.uri[1]}'

    def __init__(self, ip='localhost', port=8088):
        self.address = (ip, port)
        self.safestop = True
        const.SERVEDATA = Nomad.peer(const.USERNAME, self.address)
        self.peersock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        const.OBJTHREAD = self.start_thread(self.initiate)

    def initiate(self):
        const.HANDLECALL.wait()
        with self.peersock as sock:
            sock.bind(self.address)
            sock.listen()
            while self.safestop:
                readables, _, _ = select.select([sock], [], [], 0.001)
                if sock not in readables:
                    continue
                _conn, _ = sock.accept()
                activitylog(f"New connection from {_[0]}:{_[1]}")
                Nomad.currently_in_connection[_conn] = True
                const.ACTIVEPEERS.append(
                    self.start_thread(Nomad.get_data, args=(_conn,)))
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
                        sock.send(_datalen)
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
            file = PeerFILE(path=filedata, sock=sock)
            file.send_meta_data()
            file.send_file()
            sock.close()

    @staticmethod
    def get_data(cls, _conn: socket.socket):
        while cls.currently_in_connection[_conn]:

            try:
                readables, _, _ = select.select([_conn], [], [], 0.001)
                if _conn not in readables:
                    continue
                get_datalen = struct.unpack('!I', _conn.recv(4))[0]
                getdata_data = _conn.recv(get_datalen)
                print(f"data from {_conn.getpeername()} :", getdata_data)  # debug
                if getdata_data.decode(const.FORMAT) == const.CMDSENDFILE:
                    time.sleep(0.1)
                    getdata_thread = cls.start_thread(cls.recv_file, args=(_conn,))
                if getdata_data:
                    asyncio.run(handle.feeduserdata(getdata_data, _conn.getpeername()))
            except Exception as e:
                errorlog(f"Error at get_data() from core/nomad at line 92 :{e}")

        return

    @staticmethod
    def recv_file(cls, _conn: socket.socket):
        getdata_file = PeerFILE(sock=_conn)
        getdata_file.recv_meta_data()
        getdata_file.recv_file()
        pass

    @staticmethod
    def start_thread(target=None, args=()):
        if len(args) != 0:
            threadrecv = threading.Thread(target=target, args=args)
        else:
            threadrecv = threading.Thread(target=target, daemon=True)
        threadrecv.start()
        return threadrecv

    def end(self):
        print("::Ending Nomad Object")
        self.safestop = False
        # asyncio.run(notifyusers())  # notify users that this user is going offline
        self.peersock.close()

