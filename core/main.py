import avails.connectserver as connectserver
import avails.nomad as nomad
from core import constants as const


def initiate():
    const.set_constants()
    # webpage.handle.initiatecontrol()
    # webbrowser.BaseBrowser.default = "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"
    # try:
    #     webbrowser.get()
    #     webbrowser.open(f'file:///{const.CURRENTDIR}/../webpage/index.html')
    # except webbrowser.Error:
    #     logs.errorlog(f'Browser not found{sys.exc_info()[0]}')
    #     sys.exit(-1)
    # const.OBJ = nomad.Nomad(const.SERVERIP, const.SERVERPORT)
    # asyncio.get_event_loop().run_until_complete(webpage.handle.initiatecontrol())
    const.SERVEDATA = nomad.Nomad.peer(const.USERNAME, const.THISIP)
    connectserver.initiateconnection()
    const.SERVERTHREAD.join()
    return


if __name__ == "__main__":
    initiate()
