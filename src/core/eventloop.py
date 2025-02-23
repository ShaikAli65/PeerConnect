import asyncio as _asyncio
import logging
import sys

from src.avails.connect import Socket

# Set the custom event loop policy
if sys.platform == 'win32':

    class CustomIocpProactor(_asyncio.IocpProactor):
        def _get_accept_socket(self, family):  # noqa
            s = Socket(family)
            s.setblocking(False)
            s.settimeout(0)
            s.set_loop(_asyncio.get_running_loop())
            return s


    class CustomProactorEventLoop(_asyncio.ProactorEventLoop):
        def __init__(self, proactor: _asyncio.IocpProactor | None = None) -> None:
            if proactor is None:
                proactor = CustomIocpProactor()
            super().__init__(proactor)


    class CustomWindowsProactorEventLoopPolicy(_asyncio.WindowsProactorEventLoopPolicy):
        _loop_factory = CustomProactorEventLoop


    logging.getLogger().info(f'setting up event loop {sys.platform}')
    _asyncio.set_event_loop_policy(CustomWindowsProactorEventLoopPolicy())
    # _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())


def set_eager_task_factory():
    _asyncio.get_event_loop().set_task_factory(_asyncio.eager_task_factory)
