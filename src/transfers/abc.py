from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Callable

from src.avails import connect, const
from src.avails.exceptions import CancelTransfer, TransferIncomplete
from src.transfers import TransferState
from src.transfers._logger import logger


class AbstractTransferHandle(AbstractAsyncContextManager, ABC):

    @abstractmethod
    async def continue_transfer(self):
        """
        Continue Transfer called when some error happens in the initial state and that error has been recovered
        """

    @abstractmethod
    def connection_made(self, sender: Callable[[bytes], None] | connect.Sender,
                        receiver: Callable[[int], bytes] | connect.Receiver):
        """Connection has arrived that is related to this handle

        Args:
            sender(Callable[[bytes],None]): called when some data is expected to send, returns when all the data is sent
            receiver(Callable[[int],bytes]): called when some data is expected to receive, returns with bytes of length passed into
        """

    @abstractmethod
    async def cancel(self):
        """Cancel the transfer"""

    @property
    @abstractmethod
    def id(self):
        """ID of the transfer"""

    @property
    @abstractmethod
    def current_file(self):
        """File under transfer"""

    @property
    def _log_prefix(self):
        return f"[{self.__class__}]"


class AbstractSender(AbstractTransferHandle, ABC):
    """


    """

    @abstractmethod
    def __init__(self, peer_obj, transfer_id, file_list, status_updater): ...

    @abstractmethod
    async def send_files(self):
        """Send files passed into object's constructor"""


class AbstractReceiver(AbstractTransferHandle):
    @abstractmethod
    def __init__(self, peer_obj, transfer_id, download_path, status_updater): ...

    @abstractmethod
    async def recv_files(self):
        """Receive files"""


class CommonAExitMixIn(AbstractAsyncContextManager):
    __slots__ = ()

    async def __aexit__(self, exc_type, exc_value, traceback, /):
        if exc_type not in self._expected_errors:
            return

        to_return = None
        if exc_type is TransferIncomplete and self.state is not TransferState.PAUSED:
            logger.warning(
                f"state miss match at files.Receiver, conditions {exc_type=},{exc_value=}, "
                f"expected state to be PAUSED, "
                f"found {self.state=}"
            )
            to_return = True

        if exc_type is CancelTransfer and self.state is TransferState.ABORTING:
            if const.debug:
                print("SUPPRESSING error cause its expected", traceback)
            to_return = True
        self._expected_errors.clear()
        return to_return


class CommonExceptionHandlersMixIn:
    def _raise_transfer_incomplete_and_change_state(self, prev_error=None, detail=""):
        logger.debug(f'{self._log_prefix} changing state to paused')
        self.state = TransferState.PAUSED
        err = TransferIncomplete(detail)
        err.__cause__ = prev_error
        self._expected_errors.add(err)
        raise err

    def _handle_os_error(self, err, detail=""):
        logger.error(f"{self._log_prefix} got error, pausing transfer", exc_info=True)
        self.state = TransferState.PAUSED
        ti = TransferIncomplete(detail)
        ti.__cause__ = err
        self._expected_errors.add(ti)
        raise ti

    def _handle_cancel_transfer(self, ct):
        if ct in self._expected_errors:
            # we definitely reach here if we are cancelled using AbstractTransferHandle.cancel
            logger.error(f"{self._log_prefix} cancelled receiving, changing state to ABORTING", exc_info=True)
            self.state = TransferState.ABORTING
        else:
            raise

    def _handle_transfer_incomplete(self, err):
        if err in self._expected_errors:
            raise
        self._expected_errors.add(err)
        logger.error(f"{self._log_prefix} got error, pausing transfer", exc_info=True)
        self.state = TransferState.PAUSED
        raise err

    def handle_exception(self, exp):
        if isinstance(exp, CancelTransfer):
            self._handle_cancel_transfer(exp)
        if isinstance(exp, TransferIncomplete):
            self._handle_transfer_incomplete(exp)
        if isinstance(exp, OSError):
            self._handle_os_error(exp)

        raise exp
