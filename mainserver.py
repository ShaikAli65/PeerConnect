import os
import signal
import struct

from src.avails.textobject import SimplePeerText
import ipaddress
from src.avails.container import PeerDict
from concurrent.futures import ThreadPoolExecutor
from src.avails.remotepeer import RemotePeer
from src.managers.thread_manager import thread_handler
from src.configurations.configure_app import set_paths
from src.avails.waiters import ThreadActuator
from src.avails.connect import *
SERVER_PORT = 45000  # standard


class Server:
    def __init__(self,host, port):
        self.addr = (host, port)
        self.id = int(ipaddress.ip_address(host))
        self.peer_list = PeerDict()
        self.thread_pool = ThreadPoolExecutor(10, thread_name_prefix='peer-connect-server')
        self.controller = ThreadActuator(None)

    def givelist(self, client: soc.socket):

        client.send(struct.pack('!Q', len(self.peer_list)))
        for peer in self.peer_list:
            peer.send_serialized(client)
        print('::sent list to client :', client.getpeername())

    def validate(self, client):
        try:
            newuser = RemotePeer.deserialize(client)
            print('::got new user :', newuser.username, "ip: ", client.getsockname(), 'status :', newuser.status)
            if newuser.status == 0:
                print('::removing user :', repr(newuser))
                self.peer_list.remove_peer(newuser.id)
            else:
                SimplePeerText(client, const.SERVER_OK).send()
                print('::adding user', repr(newuser))
                self.givelist(client)
                self.peer_list.add_peer(newuser)
            print(">> new list :", self.peer_list)

        except socket.error as e:
            print(f'::got {e} closing connection')
            client.close() if client else None

    def start_server(self):
        print(">> started")
        server_sock = create_server(self.addr, family=const.IP_VERSION, backlog=10)
        while True:
            reads, _, _ = select.select([self.controller, server_sock], [], [], 1)
            if self.controller.to_stop:
                return
            c_sock, c_addr = server_sock.accept()
            print(">> new connection", c_addr)
            self.thread_pool.submit(self.validate, c_sock)

    def endserver(self,signum=None, frame=None):
        print(signum, frame)
        self.controller.signal_stopping()


def initiate_server():
    import src.webpage_handlers.handle_signals as sender

    pass


if __name__ == '__main__':
    import src.configurations.boot_up as boot_up
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    set_paths()
    boot_up.initiate()
    print('server:', const.THIS_IP,SERVER_PORT)
    const.IP_VERSION = socket.AF_INET6
    server = Server(host=const.THIS_IP, port=SERVER_PORT)
    signal.signal(signal.SIGINT, server.endserver)
    print('id    :', server.id)
    server.start_server()
