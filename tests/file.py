import asyncio
import hashlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import _path  # noqa
from src.avails import DataWeaver, const
from src.conduit import handledata, headers
from src.core.app import provide_app_ctx
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


@provide_app_ctx
async def test_file_transfer(_config, *, app_ctx=None):
    file_paths = (
        r"C:\Users\7862s\Desktop\25huizengek1-vitune.txt",
        r"C:\Users\7862s\Desktop\cse.ap.gov.in_TISPreviewPage_0531174.pdf",
        r"C:\Users\7862s\Desktop\How Can a Python Program Block Itself.pptx",
        r"C:\Users\7862s\Desktop\lnmh7c4kelr81.png",
        r"C:\Users\7862s\Desktop\profile.jpg",
    )
    await app_ctx.in_network.wait()
    peer = get_a_peer()
    data = DataWeaver(
        header=headers.HANDLE.SEND_FILE,
        peer_id=peer.peer_id,
        content={"paths": file_paths},
    )
    if _config.test_mode == "host":
        hash_tasks = hasher(file_paths)

    print("STARTING file transfer test")
    await handledata.send_file(data)

    if _config.test_mode == "host":
        hashes = await asyncio.gather(*hash_tasks)  # noqa
        sent_file_paths = [const.PATH_DOWNLOAD / Path(x).name for x in file_paths]

        sent_hashes = await asyncio.gather(*hasher(sent_file_paths))

        assert set(hashes) == set(sent_hashes), "hashes not matching"
        print("file transfer test passed")


@provide_app_ctx
async def test_bigfile_transfer(_config, *, app_ctx=None):
    file_paths = (
        r"D:\backup.tar.gz",
        # r"D:\Movies\Predestination.2014.720p.BluRay.x264.700MB-[Mkvking.com].mkv",
    )
    await app_ctx.in_network.wait()
    peer = get_a_peer()
    data = DataWeaver(
        header=headers.HANDLE.SEND_FILE,
        peer_id=peer.peer_id,
        content={"paths": file_paths},
    )

    print("STARTING file transfer test")
    await handledata.send_big_file(data)


def _clear_download_dir():
    from pathlib import Path
    p = Path(const.PATH_DOWNLOAD, const.APP_NAME)
    if input(f"removing {p} are you sure ([Y/y] / [N/n])?") in ('y', 'Y'):
        for i in p.glob('*'):
            i.unlink()


if __name__ == "__main__":
    file_transfer1 = State("test file transfer", test_file_transfer, config, is_blocking=True)
    file_transfer2 = State(
        "test big file transfer", test_bigfile_transfer, config, is_blocking=True
    )
    start_test1((file_transfer1, file_transfer2), ())
