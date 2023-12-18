import socket
import threading
import struct
from webpage import handle
import logs
from core import constants as const


class Nomad:
    currentlyinconnection = {}

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

    def send(self, _touser, _data: str):
        if _data:
            _data = _data.encode(const.FORMAT)
            _datalen = struct.pack('!I', len(_data))
            for _ in range(5):

                try:
                    with self.peersock as sock:
                        sock.connect(_touser.uri)
                        sock.send(_datalen)
                        sock.sendall(_data)
                    break
                except Exception as e:
                    logs.errorlog(f"Error in sending data: {e}")
                    continue

        return

    def initiate(self):
        with self.peersock as sock:
            sock.bind(self.address)
            sock.listen()
            while self.safestop:
                _conn, _ = sock.accept()
                logs.activitylog(f"New connection from {_[0]}:{_[1]}")
                Nomad.currentlyinconnection[_conn] = True
                const.ACTIVEPEERS.append(
                    self.start_thread(Nomad.getdata, args=_conn).isAlive())
        return

    @staticmethod
    def getdata(cls,_conn):
        while cls.currentlyinconnection[_conn]:
            try:
                _datalen = struct.unpack('!I', _conn.recv(4))[0]
                _data = _conn.recv(_datalen).decode(const.FORMAT)
                if _data:
                    print(_data)
                    handle.feeduserdata(_data)
            except Exception as e:
                logs.errorlog(f"Error handling connection: {e}")
        return

    @staticmethod
    def start_thread(cls, target=None, args=()):
        if len(args) == 0:
            threadrecv = threading.Thread(target=target, args=args)
        else:
            threadrecv = threading.Thread(target=target, daemon=True)
        threadrecv.start()
        return threadrecv

    def end(self):
        self.safestop = False
        self.peersock.close()

    def __del__(self):
        self.end()
