import asyncio

from src.avails import use
from src.core.app import App


class AnotherRunner(asyncio.Runner):  # noqa # dirty dirty dirty
    def __init__(self, *, app_ctx, debug=None, loop_factory=None):
        self.app_ctx: App = app_ctx
        super().__init__(debug=debug, loop_factory=loop_factory)

    @use.override
    def _on_sigint(self, signum, frame, main_task):
        self.app_ctx.finalizing.set()
        self.app_ctx.state_manager_handle.state_queue.put_nowait(None)
        return super()._on_sigint(signum, frame, main_task)
