import socket
import threading
import struct
from webpage import handle
import logs
import constants as const


class Nomad:
    def __init__(self, ip='localhost', port=8088):
        self.address = (ip, port)
        self.safestop = True
        self.peersock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.start_thread()

    def start_thread(self):
        threadrecv = threading.Thread(target=self.initiate, daemon=True)
        threadsend = threading.Thread(target=self.send, daemon=True)
        threadrecv.start()
        threadsend.start()

    def send(self,_touser,_data):
        if _data:
            _data = _data.encode(const.FORMAT)
            _datalen = struct.pack('!I', len(_data))
            for _ in range(5):

                try:
                    with self.peersock as sock:
                        sock.connect(_touser)
                        sock.sendall(_datalen)
                        sock.sendall(_data)
                except Exception as e:
                    logs.errorlog(f"Error sending data: {e}")

                    continue
                else:
                    break

    def initiate(self):
        with self.peersock as sock:
            sock.bind(self.address)
            sock.listen()
            while self.safestop:
                _conn, _ = sock.accept()

                try:
                    _datalen = struct.unpack('!I', _conn.recv(4))[0]
                    _data = _conn.recv(_datalen).decode(const.FORMAT)
                    if _data:
                        print(_data)
                        handle.feeduserdata(_data)
                except Exception as e:
                    logs.errorlog(f"Error handling connection: {e}")
                    break

    def end(self):
        self.safestop = False
        self.peersock.close()

    def __del__(self):
        self.end()
