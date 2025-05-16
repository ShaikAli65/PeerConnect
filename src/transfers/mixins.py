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
        state = getattr(self, "state")
        transfer_task = getattr(self, "transfer_task")
        expected_exps = getattr(self, "_expected_exps")

        if state not in (TransferState.SENDING, TransferState.RECEIVING):
            raise InvalidStateError(f"state is not expected to be in {state=}")

        assert transfer_task.done() is False, "main task is done"

        setattr(self, "should_stop", True)
        expected_exps.add(ct := CancelTransfer())
        transfer_task.cancel(ct)
        await transfer_task


class CommonAExitMixIn(AbstractAsyncContextManager):
    __slots__ = ()

    async def __aexit__(self, exc_type, exc_value, traceback, /):

        # extract the hidden cancel transfer put by CommonCancelMixIn.cancel
        # if present
        if exc_type is CancelledError and any(exc_value.args):

            if (
                  isinstance(cancel_transfer := exc_value.args[0], CancelTransfer)
                  and getattr(self, "state") is TransferState.ABORTING
                  and cancel_transfer in getattr(self, "_expected_exps")
            ):
                return

        if exc_type not in getattr(self, "_expected_exps"):
            return

        if (
              exc_type is TransferIncomplete
              and getattr(self, "state") is not TransferState.PAUSED
        ):
            _logger.warning(
                f"state miss match at files.AbstractTransferHandle, conditions {exc_type=},{exc_value=}, "
                f"expected state to be PAUSED, "
                f"found state={getattr(self, 'state')}"
            )
        getattr(self, "_on_completion_event").set()
        getattr(self, "_expected_exps").clear()
        return None


class ExceptionRouterMixIn:
    def _raise_transfer_incomplete_and_change_state(self, prev_error=None, detail=""):
        log_prefix = getattr(self, "_log_prefix")
        expected_exps = getattr(self, "_expected_exps")

        _logger.debug(f"{log_prefix} changing state to paused")
        self.state = TransferState.PAUSED
        err = TransferIncomplete(prev_error, f"{detail=}")
        err.__cause__ = prev_error
        expected_exps.add(err)
        raise err

    def _handle_os_error(self, err, detail=""):
        log_prefix = getattr(self, "_log_prefix")
        expected_exps = getattr(self, "_expected_exps")

        _logger.error(f"{log_prefix} got error, pausing transfer", exc_info=True)
        self.state = TransferState.PAUSED

        if isinstance(err, ConnectionError):
            ti = TransferIncomplete(err, f"{detail=}")
        else:
            ti = TransferIncomplete(detail)
            ti.__cause__ = err

        expected_exps.add(ti)
        raise ti

    def _handle_cancel_transfer(self, ct):
        log_prefix = getattr(self, "_log_prefix")
        expected_exps = getattr(self, "_expected_exps")

        if ct in expected_exps:
            # we definitely reach here if we are cancelled using AbstractTransferHandle.cancel
            _logger.error(
                f"{log_prefix} cancelled receiving, changing state to ABORTING",
                exc_info=True,
            )
            self.state = TransferState.ABORTING
        else:
            raise

    def _handle_transfer_incomplete(self, err):
        log_prefix = getattr(self, "_log_prefix")
        expected_exps = getattr(self, "_expected_exps")

        if err in expected_exps:
            raise

        expected_exps.add(err)
        _logger.error(f"{log_prefix} got error, pausing transfer", exc_info=True)
        self.state = TransferState.PAUSED
        raise err

    P = ParamSpec("P")  # Parameter specification
    R = TypeVar("R")  # Return type

    def wrap_exp_handling(
          self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
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
        setattr(self, "state", TransferState.PAUSED)
        _logger.debug(f"pausing transfer, id={getattr(self, 'id')}")
        getattr(self, "net_receiver").pause()
        getattr(self, "net_sender").pause()

    def resume(self):
        if getattr(self, "state") is not TransferState.PAUSED:
            return
        _logger.debug(f"resuming transfer, id={getattr(self, 'id')}")
        setattr(self, "state", TransferState.SENDING)
        getattr(self, "net_receiver").resume()
        getattr(self, "net_sender").resume()
