from core import *


class ErrorManager:
    """A class to manage errors and exceptions."""

    def __init__(self, error:Exception, message:str) -> None:
        pass

    @staticmethod
    def error_log(*args) -> None:
        """Logs an error to the console.

        Args:
            *args: The error message to log.
        """
        with const.PRINT_LOCK:
            print(*args)

    @staticmethod
    def activity_log(*args) -> None:
        """Logs an activity to the console.

        Args:
            *args: The activity message to log.
        """
        with const.PRINT_LOCK:
            print(*args)

