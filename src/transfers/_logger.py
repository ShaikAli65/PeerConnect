import logging
import sys
from typing import TYPE_CHECKING

logger = logging.getLogger(__package__)

# make this module a logger
sys.modules[__name__] = logger

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Mapping, TypeAlias

    _SysExcInfoType: TypeAlias = tuple[type[BaseException], BaseException, TracebackType | None] | tuple[
        None, None, None]
    _ExcInfoType: TypeAlias = None | bool | _SysExcInfoType | BaseException


    def debug(
          msg: object,
          *args: object,
          exc_info: _ExcInfoType = None,
          stack_info: bool = False,
          stacklevel: int = 1,
          extra: Mapping[str, object] | None = None,
    ) -> None:
        ...


    def info(
          msg: object,
          *args: object,
          exc_info: _ExcInfoType = None,
          stack_info: bool = False,
          stacklevel: int = 1,
          extra: Mapping[str, object] | None = None,
    ) -> None:
        ...


    def warning(
          msg: object,
          *args: object,
          exc_info: _ExcInfoType = None,
          stack_info: bool = False,
          stacklevel: int = 1,
          extra: Mapping[str, object] | None = None,
    ) -> None:
        ...


    if sys.version_info < (3, 13):
        def warn(
              msg: object,
              *args: object,
              exc_info: _ExcInfoType = None,
              stack_info: bool = False,
              stacklevel: int = 1,
              extra: Mapping[str, object] | None = None,
        ) -> None: ...


    def error(
          msg: object,
          *args: object,
          exc_info: _ExcInfoType = None,
          stack_info: bool = False,
          stacklevel: int = 1,
          extra: Mapping[str, object] | None = None,
    ) -> None:
        ...


    def exception(
          msg: object,
          *args: object,
          exc_info: _ExcInfoType = True,
          stack_info: bool = False,
          stacklevel: int = 1,
          extra: Mapping[str, object] | None = None,
    ) -> None:
        ...


    def critical(
          msg: object,
          *args: object,
          exc_info: _ExcInfoType = None,
          stack_info: bool = False,
          stacklevel: int = 1,
          extra: Mapping[str, object] | None = None,
    ) -> None:
        ...


    def log(
          level: int,
          msg: object,
          *args: object,
          exc_info: _ExcInfoType = None,
          stack_info: bool = False,
          stacklevel: int = 1,
          extra: Mapping[str, object] | None = None,
    ) -> None:
        ...
