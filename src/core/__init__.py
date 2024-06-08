# Importing the required modules and packages for files across the project

import src.avails.connect as connect
from src.avails.constants import LIST_OF_PEERS as peer_list
from src.avails.waiters import *
from logs import error_log
from logs import activity_log
from logs import server_log


import threading
import socket
import time
import json
import asyncio
import struct
import select
import selectors
import os

from collections.abc import MutableSet
from typing import Union, Dict, Tuple
import src.avails.constants as const


modules = (
    threading, socket, time, json,
    asyncio, struct, select, selectors,
    os, MutableSet, Union, Dict, Tuple,
    const, peer_list, connect,
    error_log, activity_log, server_log,
    peer_list, Union, ThreadActuator
)


class NotInUse:
    __annotations__ = {
        'function': str,
        '__doc__': str
    }
    __slots__ = 'function', '__doc__'

    def __init__(self, function):
        """
        Decorator class to mark functions as not in use or not fully tested.
        :raises ValueError : if function gets called
        Args:
        - function: The function to be decorated.
        """
        self.__doc__ = """This class is used to mark functions that are not currently in use or haven't been fully tested.
        By marking a function with this class, it prevents the call to the function unless explicitly allowed by the user.
        """
        self.function = function

    def __call__(self, *args, **kwargs):
        """
        Args:
        - *args: Positional arguments for the function.
        - **kwargs: Keyword arguments for the function.
        """
        raise ValueError(f"Your are not supposed to call this function :{self.function.__name__}")


def func_str(func_name):
    return f"{func_name.__name__}()\\{os.path.relpath(func_name.__code__.co_filename)}"
