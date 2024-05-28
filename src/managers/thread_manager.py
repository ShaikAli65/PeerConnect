from src.core import *
from concurrent.futures import ThreadPoolExecutor, Executor
from src.avails.waiters import ThController


socket_resources = set()

NOMAD = 1
REQUESTS = 2
FILES = 3
DIRECTORIES = 4


class _ThreadController:
    def __init__(self):
        self.main_map = {
            NOMAD: set(),
            REQUESTS: set(),
            FILES: set(),
            DIRECTORIES: set()
        }

    def save(self,thread_control: ThController, which: int):
        self.main_map.get(which).add(thread_control)

    def delete(self,thread_control: ThController,which: int):
        self.main_map.get(which).discard(thread_control)


thread_handler = _ThreadController()
