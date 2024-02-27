from core import *
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from avails import useables as use


def make_directory_structure(path: Path):
    def _fill_in(p: Path):
        for f in p.iterdir():
            if f.is_file():
                d = const.PATH_DOWNLOAD / f.relative_to(path)
                d.touch(exist_ok=True)
            elif f.is_dir():
                d = const.PATH_DOWNLOAD / f.relative_to(path)
                d.mkdir(parents=True, exist_ok=True)
                _fill_in(f)
            else:
                pass
    parent = const.PATH_DOWNLOAD / path.name
    parent.mkdir(parents=True, exist_ok=True)
    _fill_in(path)
    use.echo_print(True, f"::Created directory structure at {parent}")


def directory_sender():
    pass


def directory_reciever(_conn):
    sender_obj = const.LIST_OF_PEERS[_conn.getpeername()[0]]
    sender_obj.increment_file_count()

    return None
