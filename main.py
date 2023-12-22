# """Main entry point for the application."""
#
# import signal
# import asyncio
#
# from avails import connectserver as connectserver
# from core import constants as const, nomad as nomad
# from webpage import handle
# from logs import *
#
#
# async def end_session_async() -> bool:
#     """Asynchronously performs cleanup tasks for ending the application session.
#
#     Returns:
#         bool: True if cleanup was successful, False otherwise.
#     """
#
#     activitylog("::Initiating End Sequence")
#
#     if const.OBJ:
#         const.OBJ.end()
#
#     if const.SAFELOCKFORPAGE:
#         await handle.end()
#
#     connectserver.endconnection()
#
#     activitylog("::End Sequence Complete")
#     return True
#
#
# async def endsession(signum, frame) -> None:
#     """Handles ending the application session gracefully upon receiving SIGTERM or SIGINT signals.
#
#     Args:
#         signum (int): The signal number.
#         frame (FrameType): The current stack frame.
#     """
#
#     await asyncio.create_task(end_session_async())
#
#
# def initiate() -> int:
#     """Performs initialization tasks for the application.
#
#     Returns:
#         int: 1 on successful initialization, -1 on failure.
#     """
#
#     if not const.set_constants():
#         print("::CONFIG AND CONSTANTS NOT SET EXITING ... {SUGGESTING TO CHECK ONCE}")
#         errorlog("::CONFIG AND CONSTANTS NOT SET EXITING ...")
#         return -1
#
#     try:
#         const.SERVEDATA = nomad.Nomad.peer(const.USERNAME, const.THISIP)
#         connectserver.initiateconnection()
#         const.OBJ = nomad.Nomad(const.SERVERIP, const.SERVERPORT)
#         handle.initiatecontrol()
#     except Exception as e:
#         errorlog(f"::Exception in main.py: {e}")
#         print(f"::Exception in main.py: {e}")
#         return -1
#
#     return 1
#
#
# if __name__ == "__main__":
#     """Entry point for the application when run as a script."""
#
#     signal.signal(signal.SIGTERM, lambda signum, frame: asyncio.create_task(endsession(signum, frame)))
#     signal.signal(signal.SIGINT, lambda signum, frame: asyncio.create_task(endsession(signum, frame)))
#     initiate()
import socket as soc
import os
import struct
import timeit

s = soc.socket(soc.AF_INET, soc.SOCK_STREAM)
s.connect(('localhost', 7072))
print('connected to', s.getpeername())
path = r"C:\Users\7862s\Desktop\lockscreenbackground.jpg"


def send_file():
    with open(path, 'rb') as f:
        size = os.path.getsize(path)
        file_name = os.path.basename(path)
        print(size)
        s.sendall(struct.pack('!Q', size))
        s.sendall(struct.pack('!I', len(file_name)))
        s.sendall(file_name.encode('utf-8'))
        if s.recv(1024).decode('utf-8') == 'ready':
            while data := f.read(2048):
                s.sendall(data)
    print('sent')
    s.close()
    return True


t = timeit.timeit(send_file,number=1)
print(t)
