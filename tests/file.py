import asyncio
import functools
import hashlib
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import _path  # noqa
from src.avails import DataWeaver, const
from src.conduit import handledata, headers
from src.core.public import Dock
from src.managers.statemanager import State
from test import config, get_a_peer, start_test1


def _get_hash(file_path):
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):  # Read in 8KB chunks
            sha256.update(chunk)
    return sha256.hexdigest()


def hasher(file_paths):
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(len(file_paths)) as pool:
        hash_tasks = []
        for path in file_paths:
            r = loop.run_in_executor(pool, _get_hash, path)
            hash_tasks.append(r)
    return hash_tasks


async def test_file_transfer(_config):
    file_paths = "D:\\Movies\\Schindlers List 1993 720p UHD BluRay x264 6CH-Pahe.mkv", "D:\\Movies\\Businessman_2012_Telugu_Blu_Ray_1080p_AVC_x264_DD5_1_448Kbps_+_ESub.mkv"
    await Dock.in_network.wait()
    peer = get_a_peer()
    data = DataWeaver(
        header=headers.HANDLE.SEND_FILE,
        peer_id=peer.peer_id,
        content={
            'paths': file_paths,
        }
    )
    if _config.test_mode == "host":
        hash_tasks = hasher(file_paths)
    try:
        print("starting file transfer test")
        await handledata.send_file(data)
    except Exception:
        print("%" * 80)
        traceback.print_exc()
        raise

    if _config.test_mode == "host":
        hashes = await asyncio.gather(*hash_tasks)
        sent_file_paths = [const.PATH_DOWNLOAD / Path(x).name for x in file_paths]

        sent_hashes = await asyncio.gather(*hasher(sent_file_paths))

        assert set(hashes) == set(sent_hashes), "hashes not matching"
        print("file transfer test passed")


if __name__ == '__main__':
    file_transfer = State("test file transfer", functools.partial(test_file_transfer, config), is_blocking=True)
    start_test1((), (file_transfer,))
