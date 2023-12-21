import threading
import time
import os


import avails.connectserver as connectserver
import avails.nomad as nomad
from core import constants as const
from webpage import handle


class NotInUse(DeprecationWarning):
    """A class to denote deprecated/not currently used functions/methods/classes"""
    def __init__(self,*args,**kwargs):
        pass


def initiate():
    const.set_constants()
    th = threading.Thread(target=handle.initiatecontrol)
    th.start()
    # try:
    #     webbrowser.get()
    # webbrowser.open(f'file:///{const.CURRENTDIR}/../webpage/index.html')
    os.system(f'cd {const.PAGEPATH} && index.html')
    # except webbrowser.Error:
    #     logs.errorlog(f'Browser not found{sys.exc_info()[0]}')
    #     sys.exit(-1)
    # const.OBJ = nomad.Nomad(const.SERVERIP, const.SERVERPORT)
    # asyncio.get_event_loop().run_until_complete(webpage.handle.initiatecontrol())
    time.sleep(5)
    const.SERVEDATA = nomad.Nomad.peer(const.USERNAME, const.THISIP)
    connectserver.initiateconnection()
    const.SERVERTHREAD.join()
    return


if __name__ == "__main__":
    initiate()
