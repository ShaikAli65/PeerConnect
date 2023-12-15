import os.path
import sys
import asyncio
import webpage.handle
import webbrowser
import avails.nomad as nomad
import constants as const
import logs


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
    const.OBJ = nomad.Nomad(const.SERVERIP, const.SERVERPORT)
    # asyncio.get_event_loop().run_until_complete(webpage.handle.initiatecontrol())
    # connectserver.initiateconnection()
    return


if __name__ == "__main__":
    initiate()
