import os
import socket
import logs
import avails.nomad as nomad
THISIP = socket.gethostbyname(socket.gethostname())
CURRENTDIR = os.getcwd()
LOGDIR = os.path.join(CURRENTDIR, '../..', 'logs')
CONFIGPATH = os.path.join(CURRENTDIR, '../..', 'avails', 'config.txt')
FORMAT = 'utf-8'
THISPORT = 5000
PAGEPORT = 12347
SERVERPORT = 8088
SERVERIP = THISIP
USERNAME = ''
OBJ = None

SERVERTHREAD = None
OBJTHREAD = None


def set_constants():
    _file_path = os.path.join(CURRENTDIR, '../..', 'avails', 'config.txt')
    _variable_names = ["USERNAME", "THISPORT", "PAGEPORT", "SERVERPORT", "SERVERIP"]

    try:
        with open(_file_path, 'r') as file:
            _values = [line.split(':')[1].strip() for line in file]
    except Exception as exp:
        logs.errorlog(f'Error reading config.txt: {exp}')

    for name, value in zip(_variable_names, _values):
        try:
            globals()[name] = type(globals()[name])(value)
        except ValueError as ve:
            logs.errorlog(f'Invalid value for {name} in config.txt: {ve}')

    return
