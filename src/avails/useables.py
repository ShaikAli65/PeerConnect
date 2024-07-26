# from src.avails.waiters import *
import functools
import inspect
import itertools
import os
import platform
import subprocess
from datetime import datetime
from sys import _getframe  # noqa

from . import const

_CO_NESTED = inspect.CO_NESTED
_CO_FROM_COROUTINE = inspect.CO_COROUTINE | inspect.CO_ITERABLE_COROUTINE | inspect.CO_ASYNC_GENERATOR


# this uses code from curio package
def from_coroutine(level=2, _cache={}):  # noqa
    f_code = _getframe(level).f_code
    if f_code in _cache:
        return _cache[f_code]
    if f_code.co_flags & _CO_FROM_COROUTINE:
        _cache[f_code] = True
        return True
    else:
        if f_code.co_flags & _CO_NESTED and f_code.co_name[0] == '<':
            return from_coroutine(level + 2)
        else:
            _cache[f_code] = False
            return False


def func_str(func_name):
    return f"{func_name.__name__}()\\{os.path.relpath(func_name.__code__.co_filename)}"


def get_timeouts(initial=0.001, factor=2, max_retries=const.MAX_RETIRES, max_value=5.0):
    """
    Generate exponential backoff timeout values.

    Parameters:
    initial (float): The initial timeout value in seconds. Defaults to 0.0001.
    factor (int): The factor by which the timeout value is multiplied at each step. Defaults to 2.
    max_retries (int): The maximum number of retries. Defaults to 5.
    max_value (float): The maximum timeout value in seconds. Defaults to 5.0.

    Yields:
    float: The next timeout value in the sequence, capped by max_value.

    Example:
    >>> list(get_timeouts())
    [0.0001, 0.0002, 0.0004, 0.0008, 0.0016]

    >>> list(get_timeouts(initial=1, factor=3, max_retries=4, max_value=10))
    [1, 3, 9, 10]
    """
    current = initial
    for _ in range(max_retries):
        yield min(current, max_value)
        current *= factor


@functools.wraps(print)
def echo_print(*args, **kwargs) -> None:
    """Prints the given arguments to the console.

    Args:
        *args: The arguments to print.
    """
    with const.LOCK_PRINT:
        print(*args, **kwargs)


def open_file(content):
    if platform.system() == "Windows":
        powershell_script = f"""
        $file = "{content}"
        Invoke-Item $file
        """
        result = subprocess.run(["powershell.exe", "-Command", powershell_script], stdout=subprocess.PIPE, text=True)
        return result.stdout.strip()
    elif platform.system() == "Darwin":
        subprocess.run(["open", content])
    else:
        subprocess.run(["xdg-open", content])
    return None


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


def uniquify(string_in):
    # import uuid
    # random_str = str(uuid.uuid4())
    random_str = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{string_in}{random_str}"
