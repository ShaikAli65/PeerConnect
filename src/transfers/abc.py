import asyncio
import typing
from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, AsyncIterable, TYPE_CHECKING

from src.avails import RemotePeer
from src.avails.wire import GossipMessage
from src.net import Connection
from src.transfers._state import TransferState

if TYPE_CHECKING:
    from src.transfers.files._fileobject import FileItem
else:
    FileItem = Any


class AbstractRWBase(ABC):

    @abstractmethod
    async def close(self, *args): ...

    @abstractmethod
    def set_bounds(self, start: int, end: int): ...

    @property
    def seek_pos(self):
        """Current position of seek, relative to starting of the reader/writer"""
        return NotImplemented

    @property
    def seek_end_pos(self):
        return NotImplemented

    @property
    def seek_start_pos(self):
        return NotImplemented

    @property
    def size(self):
        return NotImplemented


class AbstractReader(AbstractRWBase):

    @asynccontextmanager
    @abstractmethod
    async def start_reading(self):
        """Start the Reader
            This is usually a context manager that returns an async iterator, or itself a async generator

        Usage::

            async with reader.start_reading() as reading:
                async for chunk in reading:
                    ...

        """
        return NotImplemented

    @property
    @abstractmethod
    def reader(self) -> typing.Generator[bytes, None, None] | None: ...


class AbstractWriter(AbstractRWBase):

    @asynccontextmanager
    @abstractmethod
    async def start_writing(self): ...

    @abstractmethod
    async def write(self, data: bytes) -> int: ...


class AbstractStatusMix(ABC):
    current_status: int

    @abstractmethod
    async def update_status(self, status):
        """
        Update the progress bar using an absolute progress value.

        This method is used when the current progress is known exactly.
        It computes the delta from the previous known state and advances
        the progress bar accordingly.

        Preferred when:
            - You're syncing to a known file position (e.g., `file_reader.seek_pos`).
            - You want to enforce a correct state, even if skipped bytes were involved.

        Args:
            status (int): The absolute number of bytes transferred so far.
        """

    @abstractmethod
    async def write_update(self, update):
        """
        Increment the progress bar by a relative value.

        This method is used when you know how many bytes were just written or read,
        but not the total. It simply bumps the progress forward.

        Preferred when:
            - You're pushing updates based on read/send chunk sizes.
            - The transfer logic doesn't track cumulative progress externally.

        Args:
            update (int): Number of bytes just transferred.
        """

    @abstractmethod
    def should_yield(self) -> bool:
        """
        Check whether the transfer should yield control at this point,
        based on the internal progress and yield frequency.

        Returns:
            bool: True if yielding is appropriate now, False otherwise.
        """

    @abstractmethod
    def status_setup(self, prefix, initial_limit, final_limit): ...

    @abstractmethod
    async def close(self): ...

    @abstractmethod
    def freeze(self):
        """Disallow status_setups"""

    @abstractmethod
    def unfreeze(self):
        """Unfreeze freeze"""


class AbstractStatusIterator(AbstractStatusMix, AsyncIterable, ABC):
    """Status mix in that can be iterated over to yield status"""


class AbstractTransferHandle(AbstractAsyncContextManager, ABC):
    status_updater: AbstractStatusMix | AbstractStatusIterator
    peer: RemotePeer
    state: TransferState
    should_stop: bool
    _expected_exps: set
    transfer_task: asyncio.Task | None

    @abstractmethod
    def start_transfer(self) -> AsyncGenerator[Any]:
        """Start the transfer

        Sends a final flag when done, commiting the transfer completion.

        Yields:
            Chunk progress indicator for external observers.
        """

    @abstractmethod
    def resume_transfer(self) -> AsyncGenerator[Any]:
        """When some error happens in the initial state and that error has been recovered"""

    @abstractmethod
    def connection_made(self, connection: Connection):
        """Connection has arrived that is related to this handle"""

    @abstractmethod
    def pause(self):
        """Temporarily pause send/recv for a moment, usually until resume is called"""

    @abstractmethod
    def resume(self):
        """Temporarily resume send/recv"""

    @abstractmethod
    async def cancel(self):
        """Cancel the transfer"""

    @property
    @abstractmethod
    def id(self):
        """ID of the transfer"""

    @property
    @abstractmethod
    def current_file(self) -> FileItem | None:
        """File under transfer"""

    @property
    def _log_prefix(self):
        return f"[{self.__class__.__name__}]"

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}("
            f"peer={self.peer}, "
            f"curr={self.current_file}, "
            f"state={self.state}, "
            f")>"
        )

    @property
    @abstractmethod
    def done(self) -> asyncio.Event:
        """Returns an Event that gets set on the completion of transfer"""


class AbstractSender(AbstractTransferHandle):
    @abstractmethod
    def __init__(
          self,
          peer_obj,
          transfer_id,
          file_list: list[FileItem | AbstractReader],
          status_updater: AbstractStatusMix | AbstractStatusIterator,
    ): ...


class AbstractReceiver(AbstractTransferHandle):
    @abstractmethod
    def __init__(
          self,
          peer_obj: RemotePeer,
          transfer_id: int | str,
          download_path: Path,
          status_updater: AbstractStatusIterator | AbstractStatusMix,
    ): ...


class AbstractRumorMessageList(ABC):
    @abstractmethod
    def sample_peers(self, message_id, sample_count):
        pass

    @abstractmethod
    def push(self, message: GossipMessage):
        pass


class AbstractRumorPolicy(ABC):
    @abstractmethod
    def __init__(self, protocol_class): ...

    @abstractmethod
    def should_rumor(self, message: GossipMessage): ...
