import hashlib

import _path  # noqa
from src.avails import DataWeaver
from src.conduit import handledata
from src.core.app import provide_app_ctx
from src.managers.statemanager import State
from test import get_a_peer, start_test1


@provide_app_ctx
async def test_dir_transfer(app_ctx):
    await app_ctx.in_network.wait()
    if p := get_a_peer():
        await handledata.new_dir_transfer(
            DataWeaver(
                peer_id=p.peer_id,
                content={
                    'path': "C:/Users/7862s/Desktop/statemachines",
                }
            )
        )


def calculate_md5(file_path):
    try:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        return "File not found"
    except PermissionError:
        return "Permission denied"


if __name__ == '__main__':
    s10 = State("test dir transfer", test_dir_transfer, is_blocking=True)
    start_test1((s10,), ())
