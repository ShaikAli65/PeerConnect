import asyncio
import mmap
import os
import sys
from typing import BinaryIO

from src.avails import constants
from src.transfers import thread_pool_for_disk_io
from ._fileio import async_open
from ._fileobject import FileItem

if sys.platform == "win32":
    # must be fully qualified name  no relative paths
    def windows_merge(fsrc: BinaryIO, fdst: BinaryIO):
        src_size = os.path.getsize(fsrc.name)
        dst_size = os.path.getsize(fdst.name)

        # Align to allocation granularity (64KB on Windows)
        allocation_granularity = mmap.ALLOCATIONGRANULARITY
        aligned_offset = (dst_size // allocation_granularity) * allocation_granularity
        map_size = dst_size + src_size - aligned_offset

        # Extend destination file
        fdst.truncate(dst_size + src_size)

        # Memory map source file
        src_map = mmap.mmap(fsrc.fileno(), src_size, access=mmap.ACCESS_READ)
        dst_map = None
        try:
            # Memory map destination file
            dst_map = mmap.mmap(
                fdst.fileno(),
                map_size,
                access=mmap.ACCESS_WRITE,
                offset=aligned_offset,
            )

            # Calculate write position relative to mapped region
            write_pos = dst_size - aligned_offset
            dst_map[write_pos: write_pos + src_size] = src_map[:]
        finally:
            src_map.close()
            if dst_map:
                dst_map.close()


    merge = windows_merge

else:
    # must be fully qualified name  no relative paths
    def others_merge(fsrc: BinaryIO, fdst: BinaryIO):
        os.sendfile(fsrc.fileno(), fdst.fileno(), 0, os.path.getsize(fdst.name))


    merge = others_merge


async def merge_all_and_delete(final_file: FileItem, parts: dict[int, FileItem]):
    # TODO: check for chances of memory full

    files = sorted(parts.items(), key=lambda x: x[0])

    async with async_open(constants.PATH_DOWNLOAD / final_file.path, "ab") as final:
        final.seek(0)

        async def asyncify_merge(_curr: BinaryIO):
            await asyncio.get_running_loop().run_in_executor(
                thread_pool_for_disk_io, merge, final, _curr
            )

        for ind, file in files:
            async with async_open(constants.PATH_DOWNLOAD / file.path, "rb") as curr:
                await asyncify_merge(curr)  # Append file2 to file1
