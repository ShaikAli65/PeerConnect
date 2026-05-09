import asyncio
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

from .. import net


class CancelOperationMixIn:
    # expected fields
    state: TransferState
    transfer_task: asyncio.Task
    should_stop: bool

    async def cancel(self):
        """Cancel the transfer"""
        state = getattr(self, "state")
        transfer_task = getattr(self, "transfer_task")

        if state not in (TransferState.SENDING, TransferState.RECEIVING):
            raise InvalidStateError(f"state is not expected to be in {state=}")

        assert transfer_task.done() is False, "main task is done"

        setattr(self, "should_stop", True)
        ct = CancelTransfer()
        transfer_task.cancel(ct)
        await transfer_task


class CommonAExitMixIn(AbstractAsyncContextManager):
    __slots__ = ()
    # expected fields
    _on_completion_event: asyncio.Event
    state: TransferState

    async def __aexit__(self, exc_type, exc_value, traceback, /):

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
        return None


class ExceptionRouterMixIn:
    # expected fields
    _log_prefix: str
    state: TransferState

    def _raise_transfer_incomplete_and_change_state(self, prev_error=None, detail=""):
        log_prefix = getattr(self, "_log_prefix")

        _logger.debug(f"{log_prefix} changing state to paused")
        self.state = TransferState.PAUSED
        err = TransferIncomplete(prev_error, f"{detail=}")
        err.__cause__ = prev_error
        raise err

    def _handle_os_error(self, err, detail=""):
        log_prefix = getattr(self, "_log_prefix")

        _logger.info(f"{log_prefix} got error, pausing transfer")
        _logger.debug("", exc_info=True)
        self.state = TransferState.PAUSED

        if isinstance(err, ConnectionError):
            ti = TransferIncomplete(err, f"{detail=}")
        else:
            ti = TransferIncomplete(detail)
            ti.__cause__ = err

        raise ti

    def _handle_cancel_transfer(self, ct):
        log_prefix = getattr(self, "_log_prefix")
        self.state = TransferState.ABORTING
        _logger.error(
            f"{log_prefix} cancelled receiving, changing state to ABORTING",
            exc_info=True,
        )

    def _handle_transfer_incomplete(self, err):
        log_prefix = getattr(self, "_log_prefix")
        _logger.error(f"{log_prefix} got error, pausing transfer")
        _logger.exception("")
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

    # expected fields
    net_receiver: net.Receiver
    net_sender: net.Sender
    state: TransferState

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
