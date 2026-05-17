import sys
import asyncio
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
