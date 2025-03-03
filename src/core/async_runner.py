import asyncio
from typing import override


class AnotherRunner(asyncio.Runner):  # noqa # dirty dirty dirty
    def __init__(self, *,finalizing_flag, debug = None, loop_factory = None):
        self.finalizing = finalizing_flag
        super().__init__(debug=debug, loop_factory=loop_factory)
    @override
    def _on_sigint(self, signum, frame, main_task):
        self.finalizing.set()
        return super()._on_sigint(signum, frame, main_task)
