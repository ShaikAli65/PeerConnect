import asyncio
import os
import shutil
import sys
from typing import BinaryIO

from src.avails import const
from src.transfers import _logger, thread_pool_for_disk_io
from ._fileio import async_open
from ._fileobject import FileItem

if not const.IS_WINDOWS:
    import posix

__doc__ = """
    A copy-paste of stdlib's `shutil.copyfile`

    Removed symlink resolving and directory based error handling, as this function use case is very specific
    to merging bigfile chunks

    See `shutil.copyfile` for more standard use case

    """

if sys.platform == "win32":
    # must be fully qualified name  no relative paths
    def windows_merge(fsrc: BinaryIO, fdst: BinaryIO):
        try:
            file_size = fsrc.tell()
        except OSError:
            file_size = 0

        if file_size > 0:
            return shutil._copyfileobj_readinto(
                fsrc, fdst, min(file_size, shutil.COPY_BUFSIZE)
            )
        else:
            shutil.copyfileobj(fsrc, fdst)


    merge = windows_merge

else:
    # must be fully qualified name  no relative paths
    def linux_merge(fsrc: BinaryIO, fdst: BinaryIO):
        if shutil._HAS_FCOPYFILE:
            try:
                shutil._fastcopy_fcopyfile(fsrc, fdst, posix._COPYFILE_DATA)
                return fdst
            except shutil._GiveupOnFastCopy:
                pass
        elif shutil._USE_CP_SENDFILE:
            try:
                shutil._fastcopy_sendfile(fsrc, fdst)
                return fdst
            except shutil._GiveupOnFastCopy:
                pass

        return shutil.copyfileobj(fsrc, fdst)


    merge = linux_merge


async def merge_all_and_delete(final_file: FileItem, parts: dict[int, FileItem]):

    files = sorted(parts.items(), key=lambda x: x[0])
    final_file.path.touch()
    async with async_open(final_file.path, "rb+") as final:
        final.seek(0, os.SEEK_END)

        async def asyncify_merge(_curr: BinaryIO):
            await asyncio.get_running_loop().run_in_executor(
                thread_pool_for_disk_io, merge, _curr, final
            )

        for ind, file in files:
            try:
                _logger.debug(
                    f"merging part[id={ind:<4},size={file.size}] cur={final.tell()}"
                )
                async with async_open(file.path, "rb") as curr:
                    await asyncify_merge(curr)  # Append part to main file
            finally:
                _logger.debug(f"removing part={ind:^4}")
                file.path.unlink()

    final_file.size = final_file.path.stat().st_size
    _logger.info(f"completed merging {final_file}")
