from src.core import *
from concurrent.futures import ThreadPoolExecutor, Executor
from src.avails.waiters import ThActuator

socket_resources = set()

NOMADS = 1
REQUESTS = 2
FILES = 3
DIRECTORIES = 4
TEXT = 5


class _ThreadControl:
    __slots__ = 'thread_map',

    def __init__(self):
        self.thread_map = {
            NOMADS: set(),
            REQUESTS: set(),
            FILES: set(),
            TEXT: set(),
            DIRECTORIES: set()
        }

    def register(self, thread_control: ThActuator, which: int):
        """
        NOMADS = 1
        REQUESTS = 2
        FILES = 3
        DIRECTORIES = 4

        :param thread_control:
        :param which:
        :return:
        """
        self.thread_map.get(which).add(thread_control)

    def delete(self, thread_control: ThActuator, which: int):
        self.thread_map.get(which).discard(thread_control)


thread_handler = _ThreadControl()
