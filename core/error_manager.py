from core import *


class ErrorManager:
    """
        A class to manage errors and exceptions.
        _todo: int: The action to take to the error.
    """

    def __init__(self, error:Exception, message:str,_todo:int) -> None:
        self.error = error
        self.message = message
        self.error_log(self.error, self.message)
        self.resolved_status = False
        self.todo = _todo

    def resolve(self,*args):
        """
            Resolves the error based on the todo value.
            todo = 0: to ignore.
            todo = 1: to take action.
            todo = 2: to log and take action.
            todo = 3: to log and ignore.
        """
        if self.todo:
            pass
        if self.todo == 1:
            pass
        elif self.todo == 2:
            pass
        elif self.todo == 3:
            pass
        self.resolved_status = True

        return None

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

