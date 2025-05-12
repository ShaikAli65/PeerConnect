from asyncio import CancelledError
from contextlib import AbstractAsyncContextManager
from typing import Callable, ParamSpec, TypeVar

from src.avails.exceptions import CancelTransfer, InvalidStateError, TransferIncomplete
from . import TransferState, _logger

__all__ = (
    "CancelOperationMixIn",
    "CommonAExitMixIn",
    "ExceptionRouterMixIn",
    "ControlMixIn",
)


class CancelOperationMixIn:
    async def cancel(self):
        """Cancel the transfer"""
        if self.state not in (TransferState.SENDING, TransferState.RECEIVING):
            raise InvalidStateError(f"state is not expected to be in {self.state=}")

        assert self.transfer_task.done() is False, "main task is done"

        self.should_stop = True
        self._expected_exps.add(ct := CancelTransfer())
        self.transfer_task.cancel(ct)
        await self.transfer_task


class CommonAExitMixIn(AbstractAsyncContextManager):
    __slots__ = ()

    async def __aexit__(self, exc_type, exc_value, traceback, /):

        # extract the hidden cancel transfer put by CommonCancelMixIn.cancel
        # if present
        to_return = None
        if exc_type is CancelledError and any(exc_value.args):

            if isinstance(cancel_transfer := exc_value.args[0], CancelTransfer) \
                  and self.state is TransferState.ABORTING \
                  and cancel_transfer in self._expected_exps:
                return

        if exc_type not in self._expected_exps:
            return

        if exc_type is TransferIncomplete and self.state is not TransferState.PAUSED:
            _logger.warning(
                f"state miss match at files.AbstractTransferHandle, conditions {exc_type=},{exc_value=}, "
                f"expected state to be PAUSED, "
                f"found {self.state=}"
            )
            to_return = True

        self._expected_exps.clear()
        return to_return


class ExceptionRouterMixIn:
    def _raise_transfer_incomplete_and_change_state(self, prev_error=None, detail=""):
        _logger.debug(f'{self._log_prefix} changing state to paused')
        self.state = TransferState.PAUSED
        err = TransferIncomplete(detail)
        err.__cause__ = prev_error
        self._expected_exps.add(err)
        raise err from prev_error

    def _handle_os_error(self, err, detail=""):
        _logger.error(f"{self._log_prefix} got error, pausing transfer", exc_info=True)
        self.state = TransferState.PAUSED
        ti = TransferIncomplete(detail)
        self._expected_exps.add(ti)
        raise ti from err

    def _handle_cancel_transfer(self, ct):
        if ct in self._expected_exps:
            # we definitely reach here if we are cancelled using AbstractTransferHandle.cancel
            _logger.error(f"{self._log_prefix} cancelled receiving, changing state to ABORTING", exc_info=True)
            self.state = TransferState.ABORTING
        else:
            raise

    def _handle_transfer_incomplete(self, err):
        if err in self._expected_exps:
            raise
        self._expected_exps.add(err)
        _logger.error(f"{self._log_prefix} got error, pausing transfer", exc_info=True)
        self.state = TransferState.PAUSED
        raise err

    P = ParamSpec('P')  # Parameter specification
    R = TypeVar('R')  # Return type

    def wrap_exp_handling(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Wraps a callable with exception handling, preserving exact argument and return types.

        Args:
            func (Callable[P, R]): The function to be wrapped.
            *args (P.args): Positional arguments for the function.
            **kwargs (P.kwargs): Keyword arguments for the function.

        Returns:
            R: Result of the function call.

        Raises:
            Exception: Any exception raised by the function, passed through handle_exception.
        """
        try:
            return func(*args, **kwargs)
        except Exception as exp:
            self.handle_exception(exp)  # may reraise

    def handle_exception(self, exp):

        if isinstance(exp, CancelTransfer):
            self._handle_cancel_transfer(exp)
        if isinstance(exp, TransferIncomplete):
            self._handle_transfer_incomplete(exp)
        if isinstance(exp, OSError):
            self._handle_os_error(exp)

        raise exp


class ControlMixIn:
    __slots__ = ()

    def pause(self):
        self.state = TransferState.PAUSED
        _logger.debug(f"pausing transfer, id={self.id}")
        self.net_sender.pause()
        self.net_receiver.pause()
        self.should_stop = True

    def resume(self):
        if self.state is not TransferState.PAUSED:
            return
        _logger.debug(f"resuming transfer, id={self.id}")
        self.state = TransferState.SENDING
        self.net_receiver.resume()
        self.net_sender.resume()
