
# Importing the required modules.
import avails.constants as const
from typing import Any, Union
from datetime import datetime
from os import path
import os
import sys


class ErrorManager:
    """
        A class to manage errors and exceptions.
        _todo: int: The action to take to the error.
    """

    def __init__(self, error, message:str,_todo:int,file:str) -> None:
        self.error = error
        self.message = message
        self.error_log(self.error, self.message)
        self.resolved_status = False
        self._todo = _todo
        self.__file = file

    def resolve(self,*args):
        """
            Resolves the error based on the todo value.
            _todo = 0: to ignore.
            _todo = 1: to take action.
            _todo = 2: to log and take action.
            _todo = 3: to log and ignore.
        """
        if self._todo:
            pass
        if self._todo == 1:
            pass
        elif self._todo == 2:
            pass
        elif self._todo == 3:
            pass
        self.resolved_status = True

        return None

    @staticmethod
    def error_log(*args) -> None:
        """Logs an error to the console.

        Args:
            *args: The error message to log.
        """
        with const.LOCK_PRINT:
            print(*args)

    @staticmethod
    def activity_log(*args) -> None:
        """Logs an activity to the console.

        Args:
            *args: The activity message to log.
        """
        with const.LOCK_PRINT:
            print(*args)

