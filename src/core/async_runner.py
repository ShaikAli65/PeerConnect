import asyncio

from src.avails import use


class AnotherRunner(asyncio.Runner):  # noqa # dirty dirty dirty
    def __init__(self, *, finalizing, debug=None, loop_factory=None):
        self._finalizing = finalizing
        super().__init__(debug=debug, loop_factory=loop_factory)

    @use.override
    def _on_sigint(self, signum, frame, main_task):
        self._finalizing.set()
        return super()._on_sigint(signum, frame, main_task)
