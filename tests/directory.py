import asyncio
import hashlib

import _path  # noqa
from src.avails import DataWeaver
from src.managers.statemanager import State
from src.webpage_handlers import handledata
from test import get_a_peer
from tests.test import start_test


async def test_dir_transfer():
    await asyncio.sleep(3)
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


def main():
    try:
        file_paths = [
            "C:\\Users\\7862s\\Downloads\\13_Fibonacci_numbers.mhtml",
            "C:\\Users\\7862s\\Downloads\\bd787bfb-5041-4443-b73b-9bc456a42f6b.pdf",
            "C:\\Users\\7862s\\Downloads\\eg.sql",
            "C:\\Users\\7862s\\Downloads\\config.seb",
            "C:\\Users\\7862s\\Downloads\\msmpisdk.msi",
            "C:\\Users\\7862s\\Downloads\\msmpisetup.exe",
            "C:\\Users\\7862s\\Downloads\\peepcode-git.pdf",
        ]
        for file_path in file_paths:
            md5_hash = calculate_md5(file_path)
            print(f": {md5_hash}")
    except FileNotFoundError:
        print("File list not found")
    except PermissionError:
        print("Permission denied for reading the file list")


if __name__ == '__main__':
    s10 = State("test dir transfer", test_dir_transfer, is_blocking=True)
    start_test(s10)
