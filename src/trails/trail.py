from src.core import *
from src.avails.textobject import DataWeaver, SimplePeerText
import src.avails.useables as useables
from src.managers import filemanager
from test import _PeerFile, _SockGroup, _FileGroup


def send_file(file_data: DataWeaver, receiver_sock: socket.socket):

    pass


def recv_file(file_data: DataWeaver):
    connection_info = file_data.content

    pass
