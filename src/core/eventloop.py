import asyncio as _asyncio
import sys

from ..avails.connect import Socket


class CustomIocpProactor(_asyncio.IocpProactor):
    ...
    def _get_accept_socket(self, family):  # noqa
        s = Socket(family)
        s.settimeout(0)
        s.set_loop(_asyncio.get_running_loop())
        # print('asdfoasdbfasbgoebgeigersiogoerigarkgnelrkneoribgoi')
        return s


class CustomProactorEventLoop(_asyncio.ProactorEventLoop):
    def __init__(self, proactor: _asyncio.IocpProactor | None = None) -> None:
        if proactor is None:
            proactor = CustomIocpProactor()
        super().__init__(proactor)


class CustomWindowsProactorEventLoopPolicy(_asyncio.WindowsProactorEventLoopPolicy):
    _loop_factory = CustomProactorEventLoop


# Set the custom event loop policy
if sys.platform == 'win32':
    print('setting up event loop',sys.platform)  # debug
    _asyncio.set_event_loop_policy(CustomWindowsProactorEventLoopPolicy())
    # _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
