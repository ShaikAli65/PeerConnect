import asyncio
import sys
from contextlib import ExitStack
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.configurations import appconfig, configure
from src.managers import logmanager


@pytest.fixture
def run_executor_inline(monkeypatch):
    def run_in_executor(loop, executor, func, *args):
        future = loop.create_future()
        try:
            future.set_result(func(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future

    monkeypatch.setattr(asyncio.BaseEventLoop, "run_in_executor", run_in_executor)


@pytest.fixture(scope="session", autouse=True)
def app_runtime():
    return appconfig.init_app_runtime()


def pytest_configure():
    configure.set_paths()
    with ExitStack() as es:
        asyncio.run(logmanager.initiate(es))
        yield
