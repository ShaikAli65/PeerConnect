import os.path
if __name__ == "__main__":
    import sys
    sys.path.append(os.path.join("C:\\Users\\7862s\\Desktop\\remotezone"))

from src.avails.textobject import DataWeaver
from src.core import *
from src.managers.filemanager import fileReceiver

if __name__ == "__main__":
    const.PATH_DOWNLOAD = "D:\\server"
    # file_data = DataWeaver(header="",content={'count':1},_id=("localhost", 8000))
    so = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    so.connect(("localhost",8000))
    const.THIS_IP = "localhost"
    file_data = DataWeaver().receive(so)
    fileReceiver(file_data)
